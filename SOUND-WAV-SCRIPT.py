# SOUND-WAV-SCRIPT.py
# Sound Wav Script
# v0.2 - Stable Edition (Track-based class system + UST import support)
#
# Usage:
#   python SOUND-WAV-SCRIPT.py                    (interactive console)
#   python SOUND-WAV-SCRIPT.py main.ss            (direct file)
#   python SOUND-WAV-SCRIPT.py main.ust           (UST file)
#   python SOUND-WAV-SCRIPT.py main.mid           (MIDI file)
#   SOUND-WAV-SCRIPT.exe main.ss                  (Windows EXE)
#   SOUND-WAV-SCRIPT.exe main.ust                 (Windows EXE - UST)
#   SOUND-WAV-SCRIPT.exe main.mid                 (Windows EXE - MIDI)

import sys
import os
import re
import math
import ast
import operator
import random
import wave
import struct
import subprocess
import platform
import shutil
import json
import importlib.util
import time
import io
import tempfile
import copy

# ============================================================
# SETTINGS
# ============================================================

SAMPLE_RATE = 44100
CHANNELS = 1
SAMPLE_WIDTH = 2

RESET = "\033[0m"

RAINBOW = [
    "\033[91m",
    "\033[93m",
    "\033[92m",
    "\033[96m",
    "\033[94m",
    "\033[95m",
]

console_color = None
rainbow_mode = False
rainbow_index = 0

VALID_INSTRUMENTS = {
    "piano", "grand_piano",
    "synth", "synth_lead", "synth_bass",
    "bass",
    "drum", "kick", "hihat", "hi_hat", "snare",
    "sine", "square", "triangle", "saw", "sawtooth"
}

# Default instrument for UST import
DEFAULT_UST_INSTRUMENT = "synth"


# ============================================================
# CONSOLE
# ============================================================

def clear_screen():
    """画面をクリア"""
    if platform.system() == "Windows":
        os.system("cls")
    else:
        os.system("clear")


def set_console_color(value):
    """コンソール色を設定（対話型コンソール用）"""
    global console_color
    global rainbow_mode

    value = value.strip()

    if value.lower() == "rainbow":
        rainbow_mode = True
        console_color = None
        clear_screen()
        cprint("Switched to rainbow mode")
        return True

    rainbow_mode = False

    if value.startswith("#"):
        value = value[1:]

    if not re.fullmatch(r"[0-9a-fA-F]{6}", value):
        cprint(f"invalid color: {value}")
        return False

    r = int(value[0:2], 16)
    g = int(value[2:4], 16)
    b = int(value[4:6], 16)

    console_color = f"\033[38;2;{r};{g};{b}m"
    
    clear_screen()
    cprint(f"Color changed to #{value.upper()}")
    return True


def cprint(text=""):
    """カラフル印字"""
    global rainbow_index

    if rainbow_mode:
        color = RAINBOW[
            rainbow_index % len(RAINBOW)
        ]

        rainbow_index += 1

        print(
            color
            + str(text)
            + RESET
        )

    elif console_color:
        print(
            console_color
            + str(text)
            + RESET
        )

    else:
        print(text)


# ============================================================
# ERROR
# ============================================================

class SWSError(Exception):
    pass


def sws_error(line, error_type, message):
    raise SWSError(
        (line, error_type, message)
    )


def show_error(error_tuple):
    """エラーを見やすく表示"""
    line, error_type, message = error_tuple
    cprint("=" * 40)
    cprint("SWS ERROR")
    cprint("=" * 40)
    cprint(f"Line: {line}")
    cprint(f"Type: {error_type}")
    cprint(f"Message: {message}")
    cprint("=" * 40)
    time.sleep(2)


def show_warning(message):
    """警告を表示"""
    cprint("=" * 40)
    cprint("SWS WARNING")
    cprint("=" * 40)
    cprint(message)
    cprint("=" * 40)
    time.sleep(1)


# ============================================================
# NOTE DATA
# ============================================================

class NoteData:
    """音符単位の属性を管理"""

    def __init__(self, pitch, slur=False, key_bypass=False, lyric=None, key="C"):
        self.pitch = pitch
        self.slur = slur
        self.key_bypass = key_bypass
        self.lyric = lyric
        self.key = key

    def to_dict(self):
        return {
            "pitch": self.pitch,
            "slur": self.slur,
            "key_bypass": self.key_bypass,
            "lyric": self.lyric,
            "key": self.key
        }


# ============================================================
# OUTPUT REQUEST
# ============================================================

class OutputRequest:
    """出力要求を内部モデル化"""

    def __init__(self, request_type, filename, line, class_name=None):
        self.type = request_type
        self.filename = filename
        self.line = line
        self.class_name = class_name

    def get_output_path(self, ss_filename):
        """SSSファイルを基準に出力パスを計算"""
        ss_dir = os.path.dirname(os.path.abspath(ss_filename))
        
        if self.filename.startswith(os.path.sep) or (os.name == 'nt' and len(self.filename) > 1 and self.filename[1] == ':'):
            output_path = self.filename
        else:
            output_path = os.path.join(ss_dir, self.filename)
        
        if self.type == "wav":
            if not output_path.lower().endswith(".wav"):
                output_path += ".wav"
        elif self.type == "midi":
            if not output_path.lower().endswith((".mid", ".midi")):
                output_path += ".mid"
        elif self.type == "ust":
            if not output_path.lower().endswith(".ust"):
                output_path += ".ust"
        elif self.type == "ss":
            if not output_path.lower().endswith(".ss"):
                output_path += ".ss"
        
        return output_path


# ============================================================
# NOTE TABLE & KEY SCALES
# ============================================================

NOTE_TABLE = {
    "C": 0, "C#": 1, "Db": 1,
    "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "F": 5, "F#": 6,
    "Gb": 6, "G": 7, "G#": 8,
    "Ab": 8, "A": 9, "A#": 10,
    "Bb": 10, "B": 11,
}

KEY_SCALES = {
    "C": [0, 2, 4, 5, 7, 9, 11],
    "G": [7, 9, 11, 0, 2, 4, 6],
    "D": [2, 4, 6, 7, 9, 11, 1],
    "A": [9, 11, 1, 2, 4, 6, 8],
    "E": [4, 6, 8, 9, 11, 1, 3],
    "B": [11, 1, 3, 4, 6, 8, 10],
    "F#": [6, 8, 10, 11, 1, 3, 5],
    "F": [5, 7, 9, 10, 0, 2, 4],
    "Bb": [10, 0, 2, 3, 5, 7, 9],
    "Eb": [3, 5, 7, 8, 10, 0, 2],
    "Ab": [8, 10, 0, 1, 3, 5, 7],
    "Db": [1, 3, 5, 6, 8, 10, 0],
    "Am": [9, 11, 0, 2, 4, 5, 7],
    "Em": [4, 5, 7, 9, 11, 0, 2],
    "Bm": [11, 0, 2, 4, 6, 7, 9],
    "F#m": [6, 7, 9, 11, 1, 3, 5],
    "C#m": [1, 2, 4, 6, 8, 9, 11],
    "G#m": [8, 9, 11, 1, 3, 5, 7],
    "Dm": [2, 3, 5, 7, 9, 10, 0],
    "Gm": [7, 8, 10, 0, 2, 3, 5],
    "Cm": [0, 1, 3, 5, 7, 8, 10],
    "Fm": [5, 6, 8, 10, 0, 1, 3],
}


def note_to_midi(note, key="C", bypass=False):
    """音名とオクターブからMIDI値を計算（key補正対応）"""

    match = re.fullmatch(
        r"([A-Ga-g](?:#|b)?)(-?\d+)",
        note.strip()
    )

    if not match:
        raise ValueError(f"invalid pitch: {note}")

    name = match.group(1)
    octave = int(match.group(2))
    name = name[0].upper() + name[1:]

    if name not in NOTE_TABLE:
        raise ValueError(f"invalid pitch: {note}")

    base_midi = NOTE_TABLE[name]
    midi_value = (octave + 1) * 12 + base_midi

    if not bypass and key in KEY_SCALES:
        scale = KEY_SCALES[key]
        semitone_in_octave = base_midi % 12

        if semitone_in_octave not in scale:
            # 差が12を跨ぐ場合もあるので、最小差に直接マップ
            best_note = min(scale, key=lambda x: abs((x - semitone_in_octave + 6) % 12 - 6))
            midi_value = (octave + 1) * 12 + best_note

    if midi_value < 0 or midi_value > 127:
        raise ValueError(f"pitch out of MIDI range: {note}")

    return midi_value


def note_to_frequency(note, key="C", bypass=False):
    """MIDIからHz周波数に変換"""

    midi = note_to_midi(note, key, bypass)

    return 440.0 * 2.0 ** ((midi - 69) / 12.0)


def midi_to_note_name(midi_num):
    """MIDI番号を音名に変換"""
    note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    octave = (midi_num // 12) - 1
    note = note_names[midi_num % 12]
    return f"{note}{octave}"


# ============================================================
# LENGTH
# ============================================================

def length_to_beats(value):
    """分母からビート数に変換"""

    value = str(value).strip()
    dotted = value.endswith("+")

    if dotted:
        value = value[:-1]

    if not value.isdigit():
        raise ValueError(f"invalid note length: {value}")

    denominator = int(value)

    if denominator <= 0:
        raise ValueError("note length must be greater than 0")

    beats = 4.0 / denominator

    if dotted:
        beats *= 1.5

    return beats


def ust_length_to_beats(ust_length):
    """UST Length（UST Lengthが480=1beat）をSWSビートに変換"""
    try:
        length_val = int(ust_length)
    except ValueError:
        raise ValueError(f"invalid UST Length: {ust_length}")
    
    if length_val <= 0:
        raise ValueError("UST Length must be greater than 0")
    
    # 480 = 1 beat
    beats = length_val / 480.0
    return beats


# ============================================================
# TEMPO MAP
# ============================================================

class TempoMap:
    """複数テンポセグメントを管理"""

    def __init__(self, initial_tempo=120.0):
        if initial_tempo <= 0:
            raise ValueError("tempo must be greater than 0")
        if not math.isfinite(initial_tempo):
            raise ValueError("tempo must be finite")
        self.segments = [(0.0, initial_tempo)]
        self.tempoconst_set = True

    def set_tempoconst(self, tempo):
        """初期テンポ設定（1回のみ）"""
        if not self.tempoconst_set:
            raise ValueError("tempoconst can only be set once")
        if tempo <= 0:
            raise ValueError("tempo must be greater than 0")
        if not math.isfinite(tempo):
            raise ValueError("tempo must be finite")
        self.segments = [(0.0, tempo)]
        self.tempoconst_set = False

    def set_tempo(self, beat_position, tempo):
        """新しいテンポセグメントを追加（newtempo）"""
        if tempo <= 0:
            raise ValueError("tempo must be greater than 0")
        if not math.isfinite(tempo):
            raise ValueError("tempo must be finite")

        self.segments = [
            (b, t) for b, t in self.segments
            if b != beat_position
        ]
        self.segments.append((beat_position, tempo))
        # 必ずソートしておく
        self.segments.sort()

    def beat_to_seconds(self, beat_position):
        """beatから実秒数に変換"""
        if beat_position < 0:
            return 0.0

        total_seconds = 0.0

        # segments は (start_beat, tempo) のリスト。順序は念のためソートしておく
        self.segments.sort()
        for i in range(len(self.segments)):
            segment_beat, tempo = self.segments[i]

            # このセグメントが開始する位置が変換位置を超えていたら以降処理は不要
            if beat_position <= segment_beat:
                break

            # このセグメントでカバーするビート数を計算
            if i + 1 < len(self.segments):
                next_beat = self.segments[i + 1][0]
                beats_in_segment = min(next_beat - segment_beat, beat_position - segment_beat)
            else:
                beats_in_segment = beat_position - segment_beat

            seconds_in_segment = beats_in_segment * 60.0 / tempo
            total_seconds += seconds_in_segment

        return total_seconds

    def beat_to_ust_length(self, beat_duration):
        """SWSのbeat長をUST Lengthに変換（基準：4分音符=480）"""
        return int(beat_duration * 480)

    def get_current_tempo(self, beat_position):
        """指定位置でのテンポを取得"""
        for i in range(len(self.segments) - 1, -1, -1):
            seg_beat, tempo = self.segments[i]
            if beat_position >= seg_beat:
                return tempo
        return self.segments[0][1]

    def beat_to_midi_ticks(self, beat_position, ppq=480):
        """beatからMIDI ticks（PPQ基準）に変換"""
        return int(beat_position * ppq)


# ============================================================
# SOUND EVENT
# ============================================================

class SoundEvent:

    def __init__(
        self, instrument, start, duration, notes, line,
        class_name=None, volume=100
    ):
        self.instrument = instrument
        self.start = start
        self.duration = duration
        self.notes = notes
        self.line = line
        self.class_name = class_name
        self.volume = volume

    @property
    def end(self):
        return self.start + self.duration

    def to_dict(self):
        """JSON互換辞書に変換"""
        notes_list = []
        for note in self.notes:
            if isinstance(note, NoteData):
                notes_list.append(note.to_dict())
            else:
                notes_list.append({"pitch": note, "slur": False, "key_bypass": False, "lyric": None, "key": "C"})

        return {
            "instrument": self.instrument,
            "start": self.start,
            "duration": self.duration,
            "notes": notes_list,
            "line": self.line,
            "class": self.class_name,
            "volume": self.volume
        }


# ============================================================
# TOKENIZER
# ============================================================

class Token:
    """トークンを表現"""
    def __init__(self, token_type, value, line_number):
        self.type = token_type
        self.value = value
        self.line = line_number
    
    def __repr__(self):
        return f"Token({self.type}, {self.value!r}, line {self.line})"


class _SourceLoopBreak(Exception):
    pass


def tokenize_ss(raw_lines):
    """
    SWSコードをトークン列に変換。
    改行は基本的に無視し、セミコロン；で文を区切る。
    コメント <...> は除去。
    """
    tokens = []
    line_number = 0
    buffer = ""
    buffer_start_line = 1
    
    for raw_line in raw_lines:
        line_number += 1
        line = raw_line.rstrip('\n\r')
        
        # コメント除去
        try:
            line = remove_comments(line, line_number)
        except SWSError:
            raise
        
        if not line:
            continue
        
        # バッファに追加（改行は空白として扱う）
        if buffer:
            buffer += " " + line
        else:
            buffer = line
            buffer_start_line = line_number
        
        # トークン化（セミコロン、括弧のカウント）
        i = 0
        while i < len(buffer):
            char = buffer[i]
            
            # 文字列リテラル
            if char == '"':
                # 文字列をスキップ
                string_start = i
                i += 1
                while i < len(buffer):
                    if buffer[i] == '"' and (i == 0 or buffer[i-1] != '\\'):
                        i += 1
                        break
                    i += 1
                string_val = buffer[string_start:i]
                tokens.append(Token("STRING", string_val, buffer_start_line))
                continue
            
            # セミコロン：文の終端
            if char == ';':
                tokens.append(Token("SEMICOLON", ";", buffer_start_line))
                i += 1
                # セミコロン後の残りをバッファに移す
                buffer = buffer[i:].lstrip()
                i = 0
                if buffer:
                    buffer_start_line = line_number
                else:
                    break
                continue
            
            # 括弧（識別子の一部として扱う可能性もあるため記録）
            if char in "()[]{}":
                tokens.append(Token("BRACKET", char, buffer_start_line))
                i += 1
                continue
            
            # 空白スキップ
            if char.isspace():
                i += 1
                continue
            
            # 識別子・数字
            if char.isalnum() or char in "_.-+#":
                start = i
                while i < len(buffer) and (buffer[i].isalnum() or buffer[i] in "_.-+#"):
                    i += 1
                word = buffer[start:i]
                tokens.append(Token("WORD", word, buffer_start_line))
                continue
            
            # その他の1文字
            tokens.append(Token("SYMBOL", char, buffer_start_line))
            i += 1
    
    # バッファに残っている内容がセミコロンなしなら警告またはエラー
    if buffer.strip():
        # 不完全な文
        sws_error(line_number, "SyntaxError", f"incomplete statement (missing semicolon): {buffer.strip()}")
    
    return tokens


def remove_comments(line, line_number):
    """<...>形式のコメントを除去（ネスト禁止、文字列内は無視）"""

    result = ""
    i = 0
    in_string = False

    while i < len(line):

        char = line[i]

        if char == '"':
            # エスケープされている"は無視
            if i == 0 or line[i-1] != '\\':
                in_string = not in_string
            result += char
            i += 1
            continue

        if not in_string and char == "<":

            i += 1
            found_close = False

            while i < len(line):
                if line[i] == "<":
                    sws_error(line_number, "SyntaxError", "comment nesting is not allowed")
                if line[i] == ">":
                    found_close = True
                    i += 1
                    break
                i += 1

            if not found_close:
                sws_error(line_number, "SyntaxError", "unclosed comment")

            continue

        result += char
        i += 1

    return result.strip()


def detect_file_encoding(filepath):
    """
    ファイルの文字コードを判定（標準ライブラリのみで実装）
    戻り値: (encoding_name, uses_replace_flag)
    優先順位:
      1. UTF-8 BOM -> 'utf-8-sig'
      2. UTF-16 LE/BE BOM -> 'utf-16'
      3. UTF-8 (strict)
      4. CP932 (strict)
      5. fallback 'utf-8' with replace (and a warning)
    """
    try:
        with open(filepath, 'rb') as f:
            raw = f.read()
    except Exception:
        # Can't read file as binary, let caller handle
        return ('utf-8', False)

    # BOM checks
    if raw.startswith(b'\xef\xbb\xbf'):
        return ('utf-8-sig', False)
    if raw.startswith(b'\xff\xfe') or raw.startswith(b'\xfe\xff'):
        # use 'utf-16' which respects BOM
        return ('utf-16', False)

    # Try decode as utf-8 strict
    try:
        raw.decode('utf-8')
        return ('utf-8', False)
    except Exception:
        pass

    # Try CP932 (shift_jis) strict
    try:
        raw.decode('cp932')
        return ('cp932', False)
    except Exception:
        pass

    # Fallback: use utf-8 with replacement and warn the user
    show_warning(f"Unable to reliably detect UST file encoding for '{os.path.basename(filepath)}'. Falling back to UTF-8 with replacement; some characters may be corrupted.")
    return ('utf-8', True)


# ============================================================
# UST PARSER → SS CODE GENERATOR
# ============================================================

class USTParser:
    """UST（UTAU Sequence Text）形式ファイルを解析してSSコードを生成"""

    def __init__(self):
        self.tempo = 120.0
        self.notes = []

    def parse_file(self, filename):
        """USTファイルを解析してSSコード（文字列）を生成"""

        if not os.path.isfile(filename):
            sws_error(1, "FileNotFoundError", f"file not found: {filename}")

        # 文字コード判定（標準ライブラリのみ）
        encoding, use_replace = detect_file_encoding(filename)

        # Read text with chosen encoding
        try:
            if use_replace:
                with open(filename, "r", encoding=encoding, errors='replace') as f:
                    lines = f.readlines()
            else:
                with open(filename, "r", encoding=encoding, errors='strict') as f:
                    lines = f.readlines()
        except UnicodeDecodeError as e:
            # Try alternate decodings before failing
            try:
                with open(filename, "r", encoding='cp932', errors='strict') as f:
                    lines = f.readlines()
                    encoding = 'cp932'
                    use_replace = False
            except Exception:
                try:
                    with open(filename, "r", encoding='utf-8', errors='replace') as f:
                        lines = f.readlines()
                        encoding = 'utf-8'
                        use_replace = True
                        show_warning(f"File '{filename}' could not be decoded strictly; using UTF-8 with replacement.")
                except Exception as e2:
                    sws_error(1, "FileError", f"failed to read UST file: {str(e2)}")
        except Exception as e:
            sws_error(1, "FileError", f"failed to read UST file: {str(e)}")

        # パース
        section = None
        current_note = {}
        current_note_line = None
        line_number = 0

        for raw_line in lines:
            line_number += 1
            # We strip trailing newline but keep content for key=value parsing
            line = raw_line.strip()

            if not line:
                continue

            # Section header
            if line.startswith("[#") and line.endswith("]"):
                inside = line[2:-1]

                # TRACKEND -> stop parsing
                if inside == "TRACKEND":
                    # commit last note if any
                    if current_note:
                        try:
                            self._process_note(current_note, current_note_line or line_number)
                        except Exception as e:
                            sws_error(current_note_line or line_number, "NoteError", str(e))
                        current_note = {}
                        current_note_line = None
                    break

                if inside == "SETTING":
                    # commit previous note if any
                    if current_note:
                        try:
                            self._process_note(current_note, current_note_line or line_number)
                        except Exception as e:
                            sws_error(current_note_line or line_number, "NoteError", str(e))
                        current_note = {}
                        current_note_line = None
                    section = "SETTING"
                    continue

                # NOTE sections are like [#0000], [#0001], i.e., numeric inside
                if inside.isdigit():
                    # New note section: commit previous note if present
                    if current_note:
                        try:
                            self._process_note(current_note, current_note_line or line_number)
                        except Exception as e:
                            sws_error(current_note_line or line_number, "NoteError", str(e))
                    # Start a fresh note dict; record the line number of section header
                    current_note = {}
                    current_note_line = line_number
                    section = "NOTE"
                    continue

                # Unknown section header - treat as error (strict)
                sws_error(line_number, "SyntaxError", f"unsupported UST section: [{inside}]")

            # key=value lines
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()

                if section == "SETTING":
                    if key == "Tempo":
                        try:
                            tempo_val = float(value)
                            if tempo_val <= 0 or tempo_val > 500:
                                raise ValueError("invalid tempo")
                            self.tempo = tempo_val
                        except Exception:
                            sws_error(line_number, "ValueError", f"invalid Tempo value: {value}")
                    # other setting keys are ignored for now
                    continue

                elif section == "NOTE":
                    # store into current_note; values are raw strings
                    current_note[key] = value
                    continue

                else:
                    # lines outside recognized sections are ignored
                    continue

            # If line is neither section header nor key=value, ignore (robust)
            continue

        # 最後のノートを処理
        if current_note:
            try:
                self._process_note(current_note, current_note_line or line_number)
            except Exception as e:
                sws_error(current_note_line or line_number, "NoteError", str(e))

        return self._generate_ss_code()

    def _process_note(self, note_dict, line_number):
        """USTノートをUSTParser内部のnoteリストへ追加"""
        # Lyric (may be absent)
        lyric = note_dict.get("Lyric", "").strip()

        # NoteNum (MIDI number) - default 60
        try:
            note_num_raw = note_dict.get("NoteNum", "60")
            note_num = int(note_num_raw)
        except Exception:
            sws_error(line_number, "ValueError", f"invalid NoteNum: {note_dict.get('NoteNum')}")

        if note_num < 0 or note_num > 127:
            sws_error(line_number, "ValueError", f"NoteNum out of range: {note_num}")

        # Length - default 480
        try:
            length_raw = note_dict.get("Length", "480")
            length = int(length_raw)
        except Exception:
            sws_error(line_number, "ValueError", f"invalid Length: {note_dict.get('Length')}")

        if length <= 0:
            sws_error(line_number, "ValueError", "Length must be greater than 0")

        # Convert length to beats
        beats = ust_length_to_beats(length)

        # Rest detection (Lyric == R or r)
        is_rest = False
        if lyric and lyric.upper() == "R":
            is_rest = True

        # Store note info
        note_info = {
            "note_num": note_num,
            "length": length,
            "beats": beats,
            "lyric": lyric if lyric else "",
            "is_rest": is_rest
        }

        self.notes.append(note_info)

    def _generate_ss_code(self):
        """パースされたUST情報からSSコード（文字列）を生成"""
        lines = []

        # Header: tempoconst
        lines.append(f'tempoconst="{self.tempo:.2f}";')
        lines.append("")

        # Events
        for note_info in self.notes:
            if note_info["is_rest"]:
                # 休符: sleep()として出力
                beats_str = self._format_beats_for_sleep(note_info["beats"])
                lines.append(f"sleep({beats_str});")
            else:
                # 通常ノート: snd()として出力
                instrument = DEFAULT_UST_INSTRUMENT
                pitch = midi_to_note_name(note_info["note_num"])
                length_str = self._beats_to_denominator(note_info["beats"])
                lyric = note_info["lyric"]

                lyric_attr = ""
                if lyric:
                    lyric_attr = f',Lyric="{lyric}"'

                lines.append(f'snd("{instrument}",{length_str},{pitch}{lyric_attr});')

        lines.append("")

        return "\n".join(lines)

    def _format_beats_for_sleep(self, beats):
        """ビート数をsleep()の引数形式に変換"""
        # UST Length 480 = 1 beat = denominator 4
        # beats を分母（denominator）に逆変換
        if beats <= 0:
            return "4"
        
        denominator = 4.0 / beats
        
        # 整数か確認
        if denominator == int(denominator):
            return str(int(denominator))
        
        # 点音符か確認（1.5倍の形式）
        dotted_denom = denominator / 1.5
        if dotted_denom == int(dotted_denom):
            return f"{int(dotted_denom)}+"
        
        # 変換不可の場合は近い値を使用
        return str(int(round(denominator)))

    def _beats_to_denominator(self, beats):
        """ビート数をsnd()の長さ引数（分母）に変換"""
        if beats <= 0:
            return "4"
        
        denominator = 4.0 / beats
        
        # 整数か確認
        if denominator == int(denominator):
            return str(int(denominator))
        
        # 点音符か確認（1.5倍の形式）
        dotted_denom = denominator / 1.5
        if dotted_denom == int(dotted_denom):
            return f"{int(dotted_denom)}+"
        
        # 変換不可の場合は近い値を使用
        return str(int(round(denominator)))


class MIDIParser:
    """Standard MIDI Fileを音符イベントとテンポ列へ変換する。"""

    def parse_file(self, filename):
        if not os.path.isfile(filename):
            sws_error(1, "FileNotFoundError", f"file not found: {filename}")

        try:
            with open(filename, "rb") as midi_file:
                data = midi_file.read()
        except Exception as e:
            sws_error(1, "FileError", f"failed to read MIDI file: {e}")

        def require_bytes(offset, length, end, label):
            if offset < 0 or length < 0 or offset + length > end:
                sws_error(1, "MIDIError", f"truncated {label}")

        def read_vlq(position, end):
            value = 0
            for _ in range(4):
                require_bytes(position, 1, end, "variable-length quantity")
                byte = data[position]
                position += 1
                value = (value << 7) | (byte & 0x7F)
                if byte < 0x80:
                    return value, position
            sws_error(1, "MIDIError", "invalid variable-length quantity")

        if len(data) < 14 or data[:4] != b"MThd":
            sws_error(1, "MIDIError", "invalid MIDI header")

        header_length = struct.unpack_from(">I", data, 4)[0]
        require_bytes(8, header_length, len(data), "MIDI header")
        if header_length < 6:
            sws_error(1, "MIDIError", "MIDI header is too short")

        midi_format, track_count, division = struct.unpack_from(">HHH", data, 8)
        if midi_format > 1:
            sws_error(1, "MIDIError", "format 2 MIDI files are not supported")
        if track_count == 0 or division == 0 or division & 0x8000:
            sws_error(
                1,
                "MIDIError",
                "MIDI must use a positive ticks-per-beat time division"
            )

        offset = 8 + header_length
        event_order = 0
        tempo_events = []
        parsed_tracks = []

        for track_index in range(track_count):
            require_bytes(offset, 8, len(data), "track header")
            if data[offset:offset + 4] != b"MTrk":
                sws_error(1, "MIDIError", "missing MIDI track chunk")

            track_length = struct.unpack_from(">I", data, offset + 4)[0]
            track_start = offset + 8
            track_end = track_start + track_length
            require_bytes(track_start, track_length, len(data), "track data")
            offset = track_end

            position = track_start
            tick = 0
            last_tick = 0
            running_status = None
            active_notes = {}
            notes = []

            while position < track_end:
                delta, position = read_vlq(position, track_end)
                tick += delta
                if tick > 0x7FFFFFFFFFFFFFFF:
                    sws_error(1, "MIDIError", "MIDI timeline is too long")
                last_tick = tick

                require_bytes(position, 1, track_end, "MIDI event")
                first_byte = data[position]
                first_data = None
                if first_byte < 0x80:
                    if running_status is None:
                        sws_error(1, "MIDIError", "invalid running status")
                    status = running_status
                    first_data = first_byte
                    position += 1
                else:
                    status = first_byte
                    position += 1
                    if status < 0xF0:
                        running_status = status

                if status == 0xFF:
                    running_status = None
                    require_bytes(position, 1, track_end, "meta event")
                    meta_type = data[position]
                    position += 1
                    length, position = read_vlq(position, track_end)
                    require_bytes(position, length, track_end, "meta event data")
                    if meta_type == 0x51 and length == 3:
                        microseconds = int.from_bytes(
                            data[position:position + 3], "big"
                        )
                        if microseconds == 0:
                            sws_error(1, "MIDIError", "MIDI tempo must be positive")
                        tempo_events.append((tick, microseconds, event_order))
                        event_order += 1
                    position += length
                    if meta_type == 0x2F:
                        break
                    continue

                if status in (0xF0, 0xF7):
                    running_status = None
                    length, position = read_vlq(position, track_end)
                    require_bytes(position, length, track_end, "system-exclusive event")
                    position += length
                    continue

                if status >= 0xF0:
                    sws_error(
                        1,
                        "MIDIError",
                        f"unsupported MIDI status byte: 0x{status:02x}"
                    )

                command = status >> 4
                channel = status & 0x0F
                data_length = 1 if command in (0xC, 0xD) else 2

                def read_data_byte():
                    nonlocal position, first_data
                    if first_data is not None:
                        value = first_data
                        first_data = None
                    else:
                        require_bytes(position, 1, track_end, "MIDI event")
                        value = data[position]
                        position += 1
                    if value >= 0x80:
                        sws_error(1, "MIDIError", "invalid MIDI data byte")
                    return value

                data1 = read_data_byte()
                data2 = read_data_byte() if data_length == 2 else 0

                if command not in (0x8, 0x9):
                    continue

                note_key = (channel, data1)
                is_note_on = command == 0x9 and data2 > 0
                if is_note_on:
                    active_notes.setdefault(note_key, []).append(
                        (tick, data1, data2)
                    )
                    continue

                queue = active_notes.get(note_key)
                if queue:
                    start_tick, pitch, velocity = queue.pop(0)
                    notes.append((
                        start_tick,
                        max(tick, start_tick + 1),
                        pitch,
                        velocity
                    ))
                    if not queue:
                        del active_notes[note_key]

            for queue in active_notes.values():
                for start_tick, pitch, velocity in queue:
                    notes.append((
                        start_tick,
                        max(last_tick, start_tick + 1),
                        pitch,
                        velocity
                    ))

            parsed_tracks.append((track_index, notes))

        return division, tempo_events, parsed_tracks


# ============================================================
# LEXER / STATEMENT BUILDER
# ============================================================

def build_statements(tokens):
    """
    トークン列から文（statement）のリストを構築。
    セミコロンまでを1つの文として扱う。
    複数行にまたがってもOK。
    """
    statements = []
    current_stmt = []
    
    for token in tokens:
        if token.type == "SEMICOLON":
            # 文の終端
            if current_stmt:
                statements.append((current_stmt, current_stmt[0].line))
            current_stmt = []
        else:
            current_stmt.append(token)
    
    # 最後の文がセミコロンなしで終わったらエラー
    if current_stmt:
        sws_error(current_stmt[0].line, "SyntaxError", "missing semicolon")
    
    return statements


def _strip_source_comments(source, syntax):
    """Remove comments without changing line numbers or string contents."""
    output = []
    index = 0
    in_string = False
    block_comment = False

    while index < len(source):
        char = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""

        if block_comment:
            if char == "*" and following == "/":
                output.extend("  ")
                index += 2
                block_comment = False
            else:
                output.append("\n" if char == "\n" else " ")
                index += 1
            continue

        if char == '"' and (index == 0 or source[index - 1] != "\\"):
            in_string = not in_string
            output.append(char)
            index += 1
            continue

        if in_string:
            output.append(char)
            index += 1
            continue

        if syntax == "JS" and char == "/" and following == "/":
            while index < len(source) and source[index] != "\n":
                output.append(" ")
                index += 1
            continue

        if syntax == "JS" and char == "/" and following == "*":
            output.extend("  ")
            index += 2
            block_comment = True
            continue

        if syntax == "SWS" and char == "<":
            line_start = source.rfind("\n", 0, index) + 1
            line_end = source.find("\n", index)
            if line_end < 0:
                line_end = len(source)
            close = source.find(">", index + 1, line_end)
            prefix = source[line_start:index].strip()
            suffix = source[close + 1:line_end].strip() if close >= 0 else ""
            if close >= 0 and (not prefix or not suffix or suffix == ";"):
                output.extend(" " * (close - index + 1))
                index = close + 1
                continue

        if syntax in ("py", "python") and char == "#" and (
            index == 0 or source[index - 1].isspace()
        ):
            while index < len(source) and source[index] != "\n":
                output.append(" ")
                index += 1
            continue

        output.append(char)
        index += 1

    if block_comment:
        sws_error(source.count("\n") + 1, "SyntaxError", "unclosed block comment")
    if in_string:
        sws_error(source.count("\n") + 1, "SyntaxError", "unclosed string")
    return "".join(output)


def _parse_indented_source(source):
    """Parse Python-like SWS blocks using the documented four-space indentation."""
    clean = _strip_source_comments(source, "py")
    roots = []
    stack = [(-1, roots)]

    for line_number, raw_line in enumerate(clean.splitlines(), 1):
        if not raw_line.strip():
            continue
        indent_text = raw_line[:len(raw_line) - len(raw_line.lstrip(" \t\u3000"))]
        indent = len(indent_text.replace("\t", "    ").replace("\u3000", "    "))
        if indent % 4:
            sws_error(line_number, "IndentationError", "indentation must use four-space or tab steps")

        while len(stack) > 1 and indent < stack[-1][0]:
            stack.pop()
        expected = 0 if len(stack) == 1 else stack[-1][0]
        if indent != expected:
            sws_error(line_number, "IndentationError", "unexpected indentation")

        text = raw_line[len(indent_text):].strip()
        block_header = None
        match = re.fullmatch(r"if\s+(.+):", text)
        if match:
            block_header = f"if ({match.group(1)})"
        else:
            match = re.fullmatch(r"elif\s+(.+):", text)
            if match:
                block_header = f"else if ({match.group(1)})"
            elif text == "else:":
                block_header = "else"
            else:
                match = re.fullmatch(
                    r"for\s+([A-Za-z_][A-Za-z0-9_]*)\s+in\s+(.+):",
                    text
                )
                if match:
                    block_header = f"for ({match.group(1)} in {match.group(2)})"
                else:
                    match = re.fullmatch(
                        r"chips\s+([A-Za-z_][A-Za-z0-9_]*):",
                        text
                    )
                    if match:
                        block_header = f"chips {match.group(1)}()"

        if block_header is not None:
            body = []
            stack[-1][1].append({
                "type": "block",
                "header": block_header,
                "body": body,
                "line": line_number
            })
            stack.append((indent + 4, body))
        else:
            stack[-1][1].append({
                "type": "statement",
                "text": text.rstrip(";").strip(),
                "line": line_number,
                "terminated": True
            })

    return roots


def _parse_curly_source(source, syntax):
    """Split SWS/JavaScript source into statements and brace-delimited blocks."""
    clean = _strip_source_comments(source, syntax)
    roots = []
    stack = [(None, roots)]
    buffer = []
    start_line = 1
    line = 1
    parentheses = 0
    brackets = 0
    in_string = False

    def text_buffer():
        return "".join(buffer).strip()

    def flush_statement(terminated):
        nonlocal buffer, start_line
        text = text_buffer()
        if text:
            stack[-1][1].append({
                "type": "statement",
                "text": text,
                "line": start_line,
                "terminated": terminated
            })
        buffer = []
        start_line = line

    for index, char in enumerate(clean):
        if not buffer and not char.isspace():
            start_line = line

        if char == '"' and (index == 0 or clean[index - 1] != "\\"):
            in_string = not in_string
            buffer.append(char)
            continue
        if in_string:
            buffer.append(char)
            continue

        if char == "(":
            parentheses += 1
        elif char == ")":
            parentheses -= 1
        elif char == "[":
            brackets += 1
        elif char == "]":
            brackets -= 1

        if parentheses < 0 or brackets < 0:
            sws_error(line, "SyntaxError", "unmatched bracket")

        if char == "{" and parentheses == 0 and brackets == 0:
            header = text_buffer()
            if not header:
                sws_error(line, "SyntaxError", "unexpected block opening")
            block = {
                "type": "block",
                "header": header,
                "body": [],
                "line": start_line
            }
            stack[-1][1].append(block)
            stack.append((block, block["body"]))
            buffer = []
            start_line = line
            continue

        if char == "}" and parentheses == 0 and brackets == 0:
            flush_statement(False)
            if len(stack) == 1:
                sws_error(line, "SyntaxError", "unexpected block closing")
            stack.pop()
            continue

        if char == ";" and parentheses == 0 and brackets == 0:
            flush_statement(True)
            continue

        if char == "\n":
            if syntax == "JS" and parentheses == 0 and brackets == 0:
                pending = text_buffer()
                is_block_header = bool(re.match(
                    r"^(?:if|else(?:\s+if)?|for|function|switch|chips)\b",
                    pending
                ))
                is_arrow_header = bool(re.match(
                    r"^(?:const|let|var)\b.*=>\s*$",
                    pending
                ))
                if pending and not is_block_header and not is_arrow_header:
                    flush_statement(True)
            line += 1
            if not buffer:
                start_line = line
            else:
                buffer.append(" ")
            continue

        buffer.append(char)

    flush_statement(False)
    if len(stack) != 1:
        block = stack[-1][0]
        sws_error(block["line"], "SyntaxError", "unclosed block")
    return roots


# ============================================================
# COMPILER - Track-based class system
# ============================================================

class Compiler:

    def __init__(self):
        self.tempo_map = TempoMap(120.0)
        self.events = []
        self.main_cursor = 0.0
        self.track_cursors = {}  # class_name -> cursor position
        self.chips = {}
        self.chips_line = {}
        self.key = "C"
        self.plugins_to_run = []
        self.output_requests = []
        self.current_ust_class = None
        self.recursion_stack = set()
        self.tempoconst_count = 0
        self.source_type = None  # "ss" or "ust"
        self.ss_source_code = ""  # 現在コンパイル中のSSコード（output.ss用）
        self.syntax = "SWS"
        self.syntax_set = False
        self.variables = {}
        self.constant_variables = set()
        self.number_variables = set()
        self.source_loop_stack = []

    def compile_file(self, filename):
        """SWS、UST、Standard MIDI Fileをコンパイル"""

        ext = os.path.splitext(filename)[1].lower()

        if ext == ".ust":
            return self.compile_ust(filename)
        elif ext == ".ss":
            return self.compile_ss(filename)
        elif ext in (".mid", ".midi"):
            return self.compile_midi(filename)
        else:
            sws_error(1, "FileError", f"unsupported file format: {ext}")

    def compile_midi(self, filename):
        """MIDIファイルの音符とテンポをSWSイベントへ変換"""
        self.source_type = "midi"
        division, tempo_events, parsed_tracks = MIDIParser().parse_file(filename)

        tempo_by_beat = {}
        for tick, microseconds, _ in sorted(
            tempo_events, key=lambda event: (event[0], event[2])
        ):
            beat = tick / division
            tempo = 60000000.0 / microseconds
            if tempo > 500:
                sws_error(
                    1,
                    "MIDIError",
                    f"tempo exceeds the SWS limit of 500 BPM: {tempo:g}"
                )
            tempo_by_beat[beat] = tempo

        initial_tempo = tempo_by_beat.get(0.0, 120.0)
        self.tempo_map = TempoMap(initial_tempo)
        for beat, tempo in sorted(tempo_by_beat.items()):
            if beat > 0:
                self.tempo_map.set_tempo(beat, tempo)

        for track_index, notes in parsed_tracks:
            grouped_notes = {}
            for start_tick, end_tick, midi_note, velocity in notes:
                start = start_tick / division
                end = max(start + 1 / division, end_tick / division)
                key = (start, end, velocity)
                grouped_notes.setdefault(key, []).append(midi_note)

            for (start, end, velocity), pitches in sorted(grouped_notes.items()):
                note_data = [
                    NoteData(
                        midi_to_note_name(pitch),
                        key_bypass=True,
                        key="C"
                    )
                    for pitch in sorted(pitches)
                ]
                self.events.append(SoundEvent(
                    "synth",
                    start,
                    end - start,
                    note_data,
                    1,
                    class_name=f"midi_track_{track_index + 1}",
                    volume=round(velocity * 100 / 127)
                ))

        if not self.events:
            sws_error(1, "MIDIError", "MIDI file contains no note events")
        self.events.sort(key=lambda event: (event.start, event.line))
        cprint(f"MIDI loaded: {len(self.events)} events")
        return self.events

    def compile_ust(self, filename):
        """USTファイルをコンパイル"""
        
        self.source_type = "ust"

        try:
            parser = USTParser()
            ss_code = parser.parse_file(filename)
            
            cprint("UST loaded")
            cprint("UST translated to SS")
            
            # SSコードを内部保存
            self.ss_source_code = ss_code
            
            # SSコードをトークン化
            raw_lines = ss_code.split('\n')
            tokens = tokenize_ss(raw_lines)
            
            # 文を構築
            statements = build_statements(tokens)
            
            # 各文をコンパイル
            for stmt_tokens, first_line in statements:
                self.compile_statement(stmt_tokens, first_line)
            
            cprint(f"Found {len(self.events)} events")

        except SWSError:
            raise
        except Exception as e:
            sws_error(1, "USTParseError", f"failed to parse UST: {str(e)}")

        return self.events

    def compile_ss(self, filename):
        """SWSファイルをコンパイル"""

        self.source_type = "ss"

        if not os.path.isfile(filename):
            sws_error(1, "FileNotFoundError", f"file not found: {filename}")

        try:
            with open(filename, "r", encoding="utf-8") as file:
                raw_lines = file.readlines()
        except UnicodeDecodeError as e:
            sws_error(1, "EncodingError", f"file encoding error: {str(e)}")
        except Exception as e:
            sws_error(1, "FileError", f"failed to read file: {str(e)}")

        # SSコードを内部保存
        self.ss_source_code = "".join(raw_lines)

        source_text = "".join(raw_lines)
        first_statement = None
        in_block_comment = False
        for line in source_text.splitlines():
            stripped = line.strip()
            if in_block_comment:
                if "*/" in stripped:
                    in_block_comment = False
                    stripped = stripped.split("*/", 1)[1].strip()
                else:
                    continue
            if stripped.startswith("/*"):
                if "*/" not in stripped[2:]:
                    in_block_comment = True
                    continue
                stripped = stripped.split("*/", 1)[1].strip()
            if stripped.startswith(("//", "#")) or re.fullmatch(r"<[^>]*>", stripped):
                continue
            if stripped:
                first_statement = stripped
                break

        if first_statement:
            first_statement = re.sub(r"\s*(?://|#).*$", "", first_statement)
            first_statement = re.sub(r"\s*<[^>]*>\s*$", "", first_statement)
        syntax_match = re.fullmatch(
            r'syntax\s*=\s*"([^"]+)"\s*;?',
            first_statement or "",
            re.IGNORECASE
        )
        if syntax_match:
            syntax_name = syntax_match.group(1).lower()
            if syntax_name in ("sws", "soundwavscript"):
                self.syntax = "SWS"
            elif syntax_name in ("js", "javascript"):
                self.syntax = "JS"
            elif syntax_name in ("py", "python"):
                self.syntax = "py"
            else:
                sws_error(1, "ValueError", f"unsupported syntax: {syntax_name}")
            self.syntax_set = True

        if self.syntax == "py":
            statements = _parse_indented_source(source_text)
        else:
            statements = _parse_curly_source(source_text, self.syntax)

        if syntax_match and statements and statements[0]["type"] == "statement" and re.match(
            r"^syntax\s*=",
            statements[0]["text"]
        ):
            statements.pop(0)
        self._compile_source_sequence(statements)

        return self.events

    def _compile_source_sequence(self, statements):
        index = 0
        while index < len(statements):
            statement = statements[index]
            if statement["type"] == "block" and re.match(
                r"^if\s*\(", statement["header"]
            ):
                chain = [statement]
                next_index = index + 1
                while next_index < len(statements):
                    following = statements[next_index]
                    if following["type"] != "block" or not re.match(
                        r"^else(?:\s+if\b)?",
                        following["header"]
                    ):
                        break
                    chain.append(following)
                    next_index += 1
                for branch in chain:
                    header = branch["header"].strip()
                    if header == "else":
                        self._compile_source_sequence(branch["body"])
                        break
                    condition_match = re.fullmatch(
                        r"(?:if|else\s+if)\s*\((.*)\)",
                        header,
                        re.DOTALL
                    )
                    if not condition_match:
                        sws_error(branch["line"], "SyntaxError", "invalid conditional block")
                    if self._evaluate_expression(
                        condition_match.group(1), branch["line"]
                    ):
                        self._compile_source_sequence(branch["body"])
                        break
                index = next_index
                continue

            if statement["type"] == "block":
                self._compile_source_block(statement)
            else:
                self._compile_source_statement(statement)
            index += 1

    def _compile_source_block(self, statement):
        header = statement["header"].strip()
        line = statement["line"]

        if header.startswith("if ") or header.startswith("else if "):
            sws_error(line, "SyntaxError", "conditional branch without preceding if")

        function_match = re.fullmatch(
            r"(?:function|func)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\((.*?)\)",
            header
        )
        arrow_match = re.fullmatch(
            r"(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\((.*?)\)\s*=>",
            header
        )
        chip_match = re.fullmatch(
            r"chips\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*\)",
            header
        )
        if function_match or arrow_match or chip_match:
            declaration = function_match or arrow_match or chip_match
            name = declaration.group(1)
            parameters = []
            if function_match or arrow_match:
                raw_parameters = declaration.group(2).strip()
                parameters = [
                    parameter.strip()
                    for parameter in split_arguments(raw_parameters)
                ] if raw_parameters else []
                if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", p) for p in parameters):
                    sws_error(line, "SyntaxError", "invalid function parameter")
                if len(set(parameters)) != len(parameters):
                    sws_error(line, "SyntaxError", "duplicate function parameter")
                if "num" in parameters:
                    sws_error(line, "SyntaxError", "'num' is reserved")
            if name in self.chips:
                sws_error(line, "NameError", f"function or chips '{name}' is already declared")
            self.chips[name] = {
                "parameters": parameters,
                "body": statement["body"],
                "line": line,
                "kind": "function" if function_match or arrow_match else "chips"
            }
            return

        if re.fullmatch(r"lp\s*\(\s*\d+\s*\)", header):
            if self.syntax != "SWS":
                sws_error(line, "SyntaxError", "lp() is only available in SWS syntax")
            count = int(re.search(r"\d+", header).group())
            if count <= 0 or count > 10000:
                sws_error(line, "ValueError", "lp count must be between 1 and 10000")
            old_num = self.variables.get("num")
            had_num = "num" in self.variables
            self.source_loop_stack.append("lp")
            try:
                for iteration in range(1, count + 1):
                    self.variables["num"] = iteration
                    try:
                        self._compile_source_sequence(statement["body"])
                    except _SourceLoopBreak:
                        break
            finally:
                self.source_loop_stack.pop()
                if had_num:
                    self.variables["num"] = old_num
                else:
                    self.variables.pop("num", None)
            return

        if header.startswith("for"):
            self._compile_source_for(header, statement["body"], line)
            return

        sws_error(line, "SyntaxError", f"unsupported block: {header}")

    def _compile_source_for(self, header, body, line):
        match = re.fullmatch(r"for\s*\((.*)\)", header, re.DOTALL)
        if not match:
            sws_error(line, "SyntaxError", f"invalid for loop: {header}")
        sections = []
        section_start = 0
        depth = 0
        for index, character in enumerate(match.group(1)):
            if character in "([": depth += 1
            elif character in ")]": depth -= 1
            elif character == ";" and depth == 0:
                sections.append(match.group(1)[section_start:index].strip())
                section_start = index + 1
        sections.append(match.group(1)[section_start:].strip())

        # Python-like and JavaScript for-of loops.
        iterable_match = re.fullmatch(
            r"(?:(?:let|const)\s+)?([A-Za-z_][A-Za-z0-9_]*)\s+(?:in|of)\s+(.+)",
            match.group(1).strip(),
            re.DOTALL
        )
        if iterable_match:
            name, expression = iterable_match.groups()
            value = self._evaluate_expression(expression, line)
            if isinstance(value, range):
                values = list(value)
            elif isinstance(value, (list, tuple, str)):
                values = list(value)
            else:
                sws_error(line, "TypeError", "for iteration requires an array or string")
            if len(values) > 8192:
                sws_error(line, "ValueError", "for loop exceeded 8192 iterations")
            self.source_loop_stack.append("for")
            try:
                for value in values:
                    self.variables[name] = value
                    try:
                        self._compile_source_sequence(body)
                    except _SourceLoopBreak:
                        break
            finally:
                self.source_loop_stack.pop()
            return

        if self.syntax == "SWS":
            sws_iterable_match = re.fullmatch(
                r"(?:number\s*\(\s*([A-Za-z_]\w*)\s*=\s*(.+?)\s*\)|"
                r"frame\s+([A-Za-z_]\w*)\s*=\s*(.+?))\s+of\s+(.+)",
                match.group(1).strip(),
                re.DOTALL
            )
            if sws_iterable_match:
                name = sws_iterable_match.group(1) or sws_iterable_match.group(3)
                initial = sws_iterable_match.group(2) or sws_iterable_match.group(4)
                is_number = sws_iterable_match.group(1) is not None
                initial_value = self._evaluate_expression(initial, line)
                if is_number and (
                    not isinstance(initial_value, (int, float))
                    or isinstance(initial_value, bool)
                ):
                    sws_error(line, "TypeError", "number variable requires a numeric value")
                self.variables[name] = initial_value
                if is_number:
                    self.number_variables.add(name)
                values = self._evaluate_expression(sws_iterable_match.group(5), line)
                if not isinstance(values, (list, tuple, str)):
                    sws_error(line, "TypeError", "for iteration requires an array or string")
                if len(values) > 8192:
                    sws_error(line, "ValueError", "for loop exceeded 8192 iterations")
                self.source_loop_stack.append("for")
                try:
                    for value in values:
                        if is_number and (
                            not isinstance(value, (int, float))
                            or isinstance(value, bool)
                        ):
                            sws_error(line, "TypeError", "number variable requires numeric values")
                        self.variables[name] = value
                        try:
                            self._compile_source_sequence(body)
                        except _SourceLoopBreak:
                            break
                finally:
                    self.source_loop_stack.pop()
                return

        if len(sections) != 3:
            sws_error(line, "SyntaxError", "for loop requires initialization, condition, and update")
        initialization, condition, update = [part.strip() for part in sections]
        if initialization:
            self._compile_source_assignment(initialization, line)
        self.source_loop_stack.append("for")
        try:
            for _ in range(8192):
                if condition and not self._evaluate_expression(condition, line):
                    return
                try:
                    self._compile_source_sequence(body)
                except _SourceLoopBreak:
                    return
                self._compile_source_update(update, line)
        finally:
            self.source_loop_stack.pop()
        sws_error(line, "ValueError", "for loop exceeded 8192 iterations")

    def _compile_source_update(self, text, line):
        match = re.fullmatch(
            r"([A-Za-z_][A-Za-z0-9_]*)\s*(\+\+|--|\+=|-=|=(?!=))\s*(.*)",
            text.strip()
        )
        if not match:
            sws_error(line, "SyntaxError", f"invalid for update: {text}")
        name, operation, expression = match.groups()
        if name not in self.variables:
            sws_error(line, "NameError", f"variable '{name}' is not defined")
        if name in self.constant_variables:
            sws_error(line, "TypeError", f"cannot reassign constant '{name}'")
        current = self.variables[name]
        if operation in ("++", "--"):
            if not isinstance(current, (int, float)) or isinstance(current, bool):
                sws_error(line, "TypeError", "for counter must be numeric")
            self.variables[name] = current + (1 if operation == "++" else -1)
            return
        value = self._evaluate_expression(expression, line)
        if operation == "=":
            self.variables[name] = value
            return
        if not isinstance(current, (int, float)) or not isinstance(value, (int, float)):
            sws_error(line, "TypeError", "numeric for updates require numbers")
        self.variables[name] = current + value if operation == "+=" else current - value

    def _compile_source_statement(self, statement):
        text = statement["text"].strip()
        line = statement["line"]
        terminated = statement["terminated"]
        if not text:
            return
        if self.syntax == "SWS" and not terminated:
            sws_error(line, "SyntaxError", "missing semicolon")

        if text in ("break", "forbreak", "end"):
            if not self.source_loop_stack:
                sws_error(line, "SyntaxError", f"{text} outside a loop")
            if text == "break" and self.syntax == "SWS":
                sws_error(line, "SyntaxError", "use forbreak or end in SWS syntax")
            if text == "forbreak" and (
                self.syntax != "SWS" or self.source_loop_stack[-1] != "for"
            ):
                sws_error(line, "SyntaxError", "forbreak is only available in an SWS for loop")
            if text == "end" and self.syntax != "SWS":
                sws_error(line, "SyntaxError", "end is only available in SWS syntax")
            raise _SourceLoopBreak()

        if re.match(r"^syntax\s*=", text):
            sws_error(line, "SyntaxError", "syntax declaration must be the first statement")

        if re.match(r"^(?:tempoconst|newtempo|key|index\.class|output\.|plugin\s*\()", text):
            tokens = tokenize_ss([text + ";"])
            for statement_tokens, _ in build_statements(tokens):
                self.compile_statement(statement_tokens, line)
            return

        if re.fullmatch(r"(?:let|const)\s+.*", text) or re.match(
            r"^(?:frame\s+\w+\s*=|number\s*\(|const\s*\()", text
        ) or re.match(r"^[A-Za-z_]\w*\s*=(?!=)", text):
            self._compile_source_assignment(text, line)
            return

        array_assignment = re.fullmatch(
            r"([A-Za-z_]\w*)\s*\[\s*(.*?)\s*\]\s*=(?!=)\s*(.+)",
            text,
            re.DOTALL
        )
        if array_assignment:
            name, index_expression, value_expression = array_assignment.groups()
            if self.syntax == "SWS" and name in self.constant_variables:
                sws_error(line, "TypeError", f"cannot modify constant array '{name}'")
            array = self.variables.get(name)
            if not isinstance(array, list):
                sws_error(line, "TypeError", f"'{name}' is not an array")
            array_index = self._evaluate_expression(index_expression, line)
            if not isinstance(array_index, int) or isinstance(array_index, bool) or not 0 <= array_index < len(array):
                sws_error(line, "IndexError", f"array index out of range: {array_index}")
            array[array_index] = self._evaluate_expression(value_expression, line)
            return

        array_method = re.fullmatch(
            r"([A-Za-z_]\w*)\.([A-Za-z_]\w*)\s*\((.*)\)",
            text,
            re.DOTALL
        )
        if array_method and array_method.group(1) in self.variables:
            if self._compile_source_array_method(*array_method.groups(), line):
                return

        output_command = {
            "SWS": "dispin",
            "JS": "console.log",
            "py": "print",
            "python": "print"
        }[self.syntax]
        if text.startswith(output_command + "("):
            args = split_arguments(text[len(output_command) + 1:-1])
            values = [self._evaluate_expression(arg, line) for arg in args]
            cprint(self._format_source_output(values, line))
            return

        sleep_match = re.fullmatch(r"(sws\.)?sleep\s*\((.*)\)", text, re.DOTALL)
        if sleep_match:
            uses_namespace = bool(sleep_match.group(1))
            if (self.syntax == "SWS") == uses_namespace:
                sws_error(line, "SyntaxError", "use sleep() in SWS and sws.sleep() in JS/Python syntax")
            arguments = split_arguments(sleep_match.group(2))
            if len(arguments) != 1:
                sws_error(line, "TypeError", "sleep() expects one duration")
            self.main_cursor += self._parse_duration_expression(arguments[0], line)
            return

        sound_match = re.fullmatch(r"(sws\.)?snd\s*\((.*)\)", text, re.DOTALL)
        if sound_match:
            uses_namespace = bool(sound_match.group(1))
            if (self.syntax == "SWS") == uses_namespace:
                sws_error(
                    line,
                    "SyntaxError",
                    "use snd() in SWS syntax and sws.snd() in JS/Python syntax"
                )
            args = split_arguments(sound_match.group(2))
            if len(args) < 3:
                sws_error(line, "SyntaxError", "snd() requires instrument, length, and pitch")
            self.compile_snd_args(line, args)
            return

        call_match = re.fullmatch(r"([A-Za-z_]\w*)\s*\((.*)\)", text, re.DOTALL)
        if call_match and call_match.group(1) == "chips":
            chip_name = call_match.group(2).strip()
            if chip_name not in self.chips:
                sws_error(line, "NameError", f"chips '{chip_name}' is not declared")
            self._call_source_function(chip_name, "", line)
            return
        if call_match and call_match.group(1) in self.chips:
            self._call_source_function(call_match.group(1), call_match.group(2), line)
            return

        tokens = tokenize_ss([text + ";"])
        for statement_tokens, _ in build_statements(tokens):
            self.compile_statement(statement_tokens, line)

    def _compile_source_assignment(self, text, line):
        constant = False
        reassign = True
        is_number = False
        match = re.fullmatch(r"(let|const)\s+([A-Za-z_]\w*)\s*=\s*(.+)", text, re.DOTALL)
        if match:
            declaration, name, expression = match.groups()
            constant = declaration == "const"
            reassign = False
        else:
            match = re.fullmatch(
                r"(?:number|const)\s*\(\s*([A-Za-z_]\w*)\s*=\s*(.*?)\s*\)",
                text,
                re.DOTALL
            )
            if match:
                name, expression = match.groups()
                constant = text.startswith("const")
                is_number = text.startswith("number")
                reassign = not constant and name in self.variables
            else:
                match = re.fullmatch(
                    r"frame\s+([A-Za-z_]\w*)\s*=\s*(.+)",
                    text,
                    re.DOTALL
                )
                if match:
                    name, expression = match.groups()
                    reassign = name in self.variables
                else:
                    match = re.fullmatch(
                        r"([A-Za-z_]\w*)\s*=(?!=)\s*(.+)",
                        text,
                        re.DOTALL
                    )
                    if not match:
                        sws_error(line, "SyntaxError", f"invalid assignment: {text}")
                    name, expression = match.groups()
                    if self.syntax == "SWS" and name not in self.variables:
                        sws_error(line, "NameError", f"variable '{name}' is not defined")
                    reassign = name in self.variables

        if name == "num":
            sws_error(line, "SyntaxError", "'num' is reserved")
        if name in self.constant_variables:
            sws_error(line, "TypeError", f"cannot reassign constant '{name}'")
        if not reassign and name in self.variables:
            sws_error(line, "NameError", f"variable '{name}' is already declared")
        if self.syntax == "JS" and reassign and name not in self.variables:
            sws_error(line, "NameError", f"variable '{name}' is not defined")
        value = self._evaluate_expression(expression, line)
        if self.syntax == "SWS" and (is_number or name in self.number_variables):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                sws_error(line, "TypeError", f"number variable '{name}' requires a numeric value")
            self.number_variables.add(name)
        self.variables[name] = value
        if constant:
            self.constant_variables.add(name)

    def _compile_source_array_method(self, name, method, raw_arguments, line):
        methods = {
            "SWS": {"topin", "bottomin", "topshift", "bottomshift", "pointshift", "pointin"},
            "JS": {"push", "unshift", "pop", "shift", "splice"},
            "py": {"append", "insert", "pop", "remove", "extend", "clear", "reverse"},
            "python": {"append", "insert", "pop", "remove", "extend", "clear", "reverse"}
        }
        if method not in methods[self.syntax]:
            return False
        if self.syntax == "SWS" and name in self.constant_variables:
            sws_error(line, "TypeError", f"cannot modify constant array '{name}'")
        array = self.variables[name]
        if not isinstance(array, list):
            sws_error(line, "TypeError", f"'{name}' is not an array")
        args = [
            self._evaluate_expression(value, line)
            for value in split_arguments(raw_arguments)
            if value.strip()
        ]
        if self.syntax == "JS" and method == "push":
            array.extend(args)
        elif self.syntax == "JS" and method == "unshift":
            array[0:0] = args
        elif method in ("append", "bottomin", "push"):
            if len(args) != 1:
                sws_error(line, "TypeError", f"{method}() expects one argument")
            array.append(args[0])
        elif method in ("topin", "unshift"):
            if len(args) != 1:
                sws_error(line, "TypeError", f"{method}() expects one argument")
            array.insert(0, args[0])
        elif method in ("pop", "shift", "topshift", "bottomshift"):
            if method == "pop" and self.syntax in ("py", "python"):
                if len(args) > 1 or not array:
                    sws_error(line, "IndexError", "pop from empty list or invalid index")
                index = args[0] if args else len(array) - 1
                if not isinstance(index, int) or not -len(array) <= index < len(array):
                    sws_error(line, "IndexError", f"pop index out of range: {index}")
                array.pop(index)
            elif method == "shift" or method == "topshift":
                if not array:
                    sws_error(line, "IndexError", "cannot remove from an empty array")
                array.pop(0)
            elif array:
                array.pop()
        elif method in ("pointshift", "pointin", "splice"):
            if not args or not isinstance(args[0], int):
                sws_error(line, "TypeError", "array index must be an integer")
            index = args[0]
            if method == "pointshift":
                if not 0 <= index < len(array):
                    sws_error(line, "IndexError", f"array index out of range: {index}")
                array.pop(index)
            elif method == "pointin":
                if len(args) != 2 or not 0 <= index <= len(array):
                    sws_error(line, "IndexError", f"array index out of range: {index}")
                array.insert(index, args[1])
            else:
                delete_count = args[1] if len(args) > 1 else len(array)
                if not isinstance(delete_count, int) or delete_count < 0:
                    sws_error(line, "TypeError", "splice delete count must be a non-negative integer")
                array[index:index + delete_count] = args[2:]
        elif method == "insert":
            if len(args) != 2:
                sws_error(line, "TypeError", "insert() expects index and value")
            array.insert(args[0], args[1])
        elif method == "remove":
            if len(args) != 1:
                sws_error(line, "TypeError", "remove() expects one argument")
            try:
                array.remove(args[0])
            except ValueError:
                sws_error(line, "ValueError", "value is not in list")
        elif method == "extend":
            if len(args) != 1 or not isinstance(args[0], list):
                sws_error(line, "TypeError", "extend() requires an array")
            array.extend(args[0])
        elif method == "clear":
            array.clear()
        elif method == "reverse":
            array.reverse()
        return True

    def _call_source_function(self, name, raw_arguments, line):
        function = self.chips[name]
        arguments = [
            self._evaluate_expression(value, line)
            for value in split_arguments(raw_arguments)
            if value.strip()
        ]
        parameters = function["parameters"]
        if len(arguments) != len(parameters):
            sws_error(line, "TypeError", f"{name}() expects {len(parameters)} arguments")
        if name in self.recursion_stack:
            sws_error(line, "RecursionError", f"function '{name}' has circular dependency")
        self.recursion_stack.add(name)
        saved_variables = self.variables
        saved_constants = self.constant_variables
        saved_number_variables = self.number_variables
        if function["kind"] == "function":
            self.variables = dict(saved_variables)
            self.constant_variables = set(saved_constants)
            self.number_variables = set(saved_number_variables)
        else:
            self.variables = {}
            self.constant_variables = set()
            self.number_variables = set()
        self.variables.update(zip(parameters, arguments))
        try:
            self._compile_source_sequence(function["body"])
        finally:
            self.variables = saved_variables
            self.constant_variables = saved_constants
            self.number_variables = saved_number_variables
            self.recursion_stack.discard(name)

    def _evaluate_expression(self, expression, line):
        source = expression.strip()
        source = source.replace("===", "==").replace("!==", "!=")
        source = source.replace("&&", " and ").replace("||", " or ")
        source = re.sub(r"!(?!=)", " not ", source)
        if self.syntax in ("JS", "SWS"):
            source = re.sub(r"\btrue\b", "True", source, flags=re.IGNORECASE)
            source = re.sub(r"\bfalse\b", "False", source, flags=re.IGNORECASE)
            source = re.sub(r"\bnull\b", "None", source, flags=re.IGNORECASE)
        if self.syntax in ("py", "python"):
            source = re.sub(r"\bTrue\b", "True", source)
            source = re.sub(r"\bFalse\b", "False", source)
            source = re.sub(r"\bNone\b", "None", source)

        try:
            tree = ast.parse(source, mode="eval")
        except SyntaxError:
            sws_error(line, "SyntaxError", f"invalid expression: {expression}")

        binary_operations = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.FloorDiv: operator.floordiv,
            ast.Mod: operator.mod,
            ast.Pow: operator.pow
        }
        comparisons = {
            ast.Eq: operator.eq,
            ast.NotEq: operator.ne,
            ast.Lt: operator.lt,
            ast.LtE: operator.le,
            ast.Gt: operator.gt,
            ast.GtE: operator.ge
        }

        def evaluate(node):
            if isinstance(node, ast.Constant):
                if isinstance(node.value, (str, int, float, bool)) or node.value is None:
                    return node.value
                sws_error(line, "TypeError", "unsupported constant")
            if isinstance(node, ast.Name):
                if node.id in ("True", "False", "None"):
                    return {"True": True, "False": False, "None": None}[node.id]
                if node.id not in self.variables:
                    sws_error(line, "NameError", f"variable '{node.id}' is not defined")
                return self.variables[node.id]
            if isinstance(node, (ast.List, ast.Tuple)):
                return [evaluate(element) for element in node.elts]
            if isinstance(node, ast.Subscript):
                value = evaluate(node.value)
                index_node = node.slice
                index = evaluate(index_node)
                if not isinstance(value, (list, tuple, str)):
                    sws_error(line, "TypeError", "indexing requires an array or string")
                if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(value):
                    sws_error(line, "IndexError", f"array index out of range: {index}")
                return value[index]
            if isinstance(node, ast.UnaryOp):
                value = evaluate(node.operand)
                if isinstance(node.op, ast.Not):
                    return not value
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    sws_error(line, "TypeError", "unary arithmetic requires a number")
                if isinstance(node.op, ast.USub):
                    return -value
                if isinstance(node.op, ast.UAdd):
                    return value
            if isinstance(node, ast.BinOp):
                left, right = evaluate(node.left), evaluate(node.right)
                operation = binary_operations.get(type(node.op))
                if operation is None:
                    sws_error(line, "SyntaxError", "unsupported arithmetic operator")
                if isinstance(node.op, ast.Add) and (
                    isinstance(left, str) or isinstance(right, str)
                ):
                    if self.syntax == "SWS" and not (
                        isinstance(left, str) and isinstance(right, str)
                    ):
                        sws_error(line, "TypeError", "SWS addition requires matching value types")
                    if self.syntax == "JS":
                        return str(left) + str(right)
                    if not (isinstance(left, str) and isinstance(right, str)):
                        sws_error(line, "TypeError", "addition requires matching value types")
                    return left + right
                if not all(isinstance(value, (int, float)) and not isinstance(value, bool)
                           for value in (left, right)):
                    sws_error(line, "TypeError", "arithmetic requires numbers")
                try:
                    return operation(left, right)
                except (ArithmeticError, OverflowError) as error:
                    sws_error(line, "ValueError", str(error))
            if isinstance(node, ast.BoolOp):
                if isinstance(node.op, ast.And):
                    for value_node in node.values:
                        if not evaluate(value_node):
                            return False
                    return True
                for value_node in node.values:
                    if evaluate(value_node):
                        return True
                return False
            if isinstance(node, ast.Compare):
                left = evaluate(node.left)
                for operation_node, comparator in zip(node.ops, node.comparators):
                    right = evaluate(comparator)
                    operation = comparisons.get(type(operation_node))
                    if operation is None:
                        sws_error(line, "SyntaxError", "unsupported comparison")
                    try:
                        if not operation(left, right):
                            return False
                    except TypeError as error:
                        sws_error(line, "TypeError", str(error))
                    left = right
                return True
            if isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else None
                namespace = None
                if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                    namespace = node.func.value.id
                    name = node.func.attr
                arguments = [evaluate(argument) for argument in node.args]
                return self._evaluate_function(name, namespace, arguments, line)
            sws_error(line, "SyntaxError", "unsupported expression")

        return evaluate(tree.body)

    def _parse_duration_expression(self, expression, line):
        text = expression.strip()
        tick_variable = re.fullmatch(r"#:\s*([A-Za-z_]\w*)", text)
        if tick_variable:
            name = tick_variable.group(1)
            if name not in self.variables:
                sws_error(line, "NameError", f"variable '{name}' is not defined")
            ticks = self.variables[name]
            if not isinstance(ticks, int) or isinstance(ticks, bool) or ticks <= 0:
                sws_error(line, "ValueError", "tick length must be a positive integer")
            return ticks / 480.0
        tick_literal = re.fullmatch(r"#(\d+)", text)
        if tick_literal:
            ticks = int(tick_literal.group(1))
            if ticks <= 0:
                sws_error(line, "ValueError", "tick length must be positive")
            return ticks / 480.0

        value = self.variables.get(text, text)
        if isinstance(value, str):
            try:
                return length_to_beats(value)
            except ValueError:
                pass
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            denominator = value
        else:
            denominator = self._evaluate_expression(text, line)
        if (
            not isinstance(denominator, (int, float))
            or isinstance(denominator, bool)
            or not math.isfinite(denominator)
            or denominator <= 0
        ):
            sws_error(line, "ValueError", "note length must be a positive number")
        return 4.0 / denominator

    def _format_source_output(self, values, line):
        if not values:
            return ""
        if not isinstance(values[0], str):
            return " ".join(str(value) for value in values)

        placeholders = re.findall(r"%[sdifocO%]", values[0])
        substitutions = [value for value in placeholders if value != "%%"]
        if self.syntax == "SWS" and len(values) > 1 and len(substitutions) != len(values) - 1:
            sws_error(
                line,
                "SyntaxError",
                "SWS dispin values must match format placeholders"
            )

        argument_index = 1

        def replace_placeholder(match):
            nonlocal argument_index
            placeholder = match.group(0)
            if placeholder == "%%":
                return "%"
            if argument_index >= len(values):
                return placeholder
            value = values[argument_index]
            argument_index += 1
            if placeholder in ("%s", "%o", "%O"):
                return str(value)
            if placeholder in ("%d", "%i", "%f"):
                try:
                    if placeholder == "%d":
                        return str(int(value))
                    if placeholder == "%i":
                        return str(int(float(value)))
                    return str(float(value))
                except (TypeError, ValueError, OverflowError):
                    sws_error(line, "TypeError", f"{placeholder} requires a numeric value")
            return ""

        formatted = re.sub(r"%[sdifocO%]", replace_placeholder, values[0])
        remaining = " ".join(str(value) for value in values[argument_index:])
        return f"{formatted} {remaining}".rstrip()

    def _evaluate_function(self, name, namespace, arguments, line):
        if name == "range" and self.syntax in ("py", "python") and namespace is None:
            if not 1 <= len(arguments) <= 3 or any(
                not isinstance(value, int) or isinstance(value, bool)
                for value in arguments
            ):
                sws_error(line, "TypeError", "range() expects one to three integer arguments")
            try:
                value_range = range(*arguments)
                length = len(value_range)
            except (OverflowError, ValueError) as error:
                sws_error(line, "ValueError", str(error))
            if length > 8192:
                sws_error(line, "ValueError", "for loop exceeded 8192 iterations")
            return list(value_range)
        if name == "log" and namespace == "math" and self.syntax in ("py", "python"):
            if len(arguments) == 1:
                if arguments[0] <= 0:
                    sws_error(line, "ValueError", "math domain error")
                return math.log(arguments[0])
            if len(arguments) == 2:
                if arguments[0] <= 0 or arguments[1] <= 0 or arguments[1] == 1:
                    sws_error(line, "ValueError", "math domain error")
                return math.log(arguments[0], arguments[1])
            sws_error(line, "TypeError", "log() expects one or two arguments")
        allowed = {
            "SWS": {"random", "floor", "round", "max", "min", "sin", "cos", "tan", "sqrt", "ln", "log"},
            "JS": {"Math": {"random", "floor", "round", "max", "min", "sin", "cos", "tan", "asin", "acos", "atan", "log", "log10", "log2"}},
            "py": {"math": {"floor", "sin", "cos", "tan", "asin", "acos", "atan", "log", "log10", "log2"}, "random": {"random"}},
            "python": {"math": {"floor", "sin", "cos", "tan", "asin", "acos", "atan", "log", "log10", "log2"}, "random": {"random"}}
        }
        if self.syntax == "SWS":
            if namespace is not None or name not in allowed["SWS"]:
                sws_error(line, "NameError", f"function '{name}' is not available in SWS syntax")
        elif namespace not in allowed[self.syntax] or name not in allowed[self.syntax][namespace]:
            sws_error(line, "NameError", f"function '{namespace}.{name}' is not available in {self.syntax} syntax")
        if name in ("random",):
            if arguments:
                sws_error(line, "TypeError", "random() takes no arguments")
            return random.random()
        if name in ("max", "min"):
            if not arguments or any(not isinstance(value, (int, float)) for value in arguments):
                sws_error(line, "TypeError", f"{name}() requires numeric arguments")
            return max(arguments) if name == "max" else min(arguments)
        if len(arguments) != 1 or not isinstance(arguments[0], (int, float)):
            sws_error(line, "TypeError", f"{name}() requires one numeric argument")
        value = arguments[0]
        if name == "floor":
            return math.floor(value)
        if name == "round":
            return round(value) if self.syntax in ("py", "python") else math.floor(value + 0.5)
        if name == "sqrt":
            if value < 0:
                sws_error(line, "ValueError", "sqrt() requires a non-negative argument")
            return math.sqrt(value)
        if name == "ln":
            if value <= 0:
                sws_error(line, "ValueError", "ln() requires a positive argument")
            return math.log(value)
        if name == "log":
            if self.syntax in ("py", "python") and len(arguments) == 2:
                return math.log(arguments[0], arguments[1])
            if value <= 0:
                sws_error(line, "ValueError", "log() requires a positive argument")
            return math.log(value)
        if name in ("sin", "cos", "tan") and self.syntax == "SWS":
            value = math.radians(value)
        try:
            return getattr(math, name)(value)
        except (ValueError, OverflowError) as error:
            sws_error(line, "ValueError", str(error))

    def compile_statement(self, tokens, line_number):
        """1つの文（トークン列）をコンパイル"""
        if not tokens:
            return
        
        # 最初のトークンで文のタイプを判定
        first_token = tokens[0]
        
        if first_token.type != "WORD":
            sws_error(line_number, "SyntaxError", f"expected keyword, got {first_token.type}")
        
        keyword = first_token.value.lower()

        if keyword in ("output.wav", "output.midi", "output.ust", "output.ss"):
            output_type = keyword.split(".", 1)[1]
            normalized = [
                Token("WORD", "output", line_number),
                Token("SYMBOL", ".", line_number),
                Token("WORD", output_type, line_number),
                *tokens[1:]
            ]
            self.compile_output(normalized, line_number)
            return

        if keyword == "index.class":
            normalized = [
                Token("WORD", "index", line_number),
                Token("SYMBOL", ".", line_number),
                Token("WORD", "class", line_number),
                *tokens[1:]
            ]
            self.compile_index_class(normalized, line_number)
            return
        
        # chips 宣言
        if keyword == "chips":
            self.compile_chips_decl(tokens, line_number)
            return
        
        # chips 呼び出し
        if keyword == "chips" and len(tokens) >= 3:
            # chips(...) の形式を確認
            if tokens[1].type == "BRACKET" and tokens[1].value == "(":
                self.compile_chips_call(tokens, line_number)
                return
        
        # lp
        if keyword == "lp":
            self.compile_lp(tokens, line_number)
            return
        
        # tempoconst
        if keyword == "tempoconst":
            self.compile_tempoconst(tokens, line_number)
            return
        
        # newtempo
        if keyword == "newtempo":
            self.compile_newtempo(tokens, line_number)
            return
        
        # key
        if keyword == "key":
            self.compile_key(tokens, line_number)
            return
        
        # index.class
        if keyword == "index":
            self.compile_index_class(tokens, line_number)
            return
        
        # output.ss
        if keyword == "output" and len(tokens) > 1:
            self.compile_output(tokens, line_number)
            return
        
        # plugin
        if keyword == "plugin":
            self.compile_plugin(tokens, line_number)
            return
        
        # sleep
        if keyword == "sleep":
            self.compile_sleep(tokens, line_number)
            return
        
        # snd
        if keyword == "snd":
            self.compile_snd(tokens, line_number)
            return
        
        sws_error(line_number, "SyntaxError", f"unknown statement: {keyword}")

    def compile_chips_decl(self, tokens, line_number):
        """chips (...) { ... } を処理"""
        # chips 名前 ( ) { ... }
        if len(tokens) < 5:
            sws_error(line_number, "SyntaxError", "invalid chips declaration")
        
        name_token = tokens[1]
        if name_token.type != "WORD":
            sws_error(line_number, "SyntaxError", "chips name must be an identifier")
        
        name = name_token.value
        
        if name in self.chips:
            sws_error(line_number, "NameError", f"chips '{name}' is already declared at line {self.chips_line[name]}")
        
        # chips (...) { ... } の内容をコレクト
        # 簡略化: トークン列から {} の中身を取り出す
        # 実装: 宣言は後で実装（複雑なため省略可能）
        sws_error(line_number, "SyntaxError", "chips declaration not yet fully supported in multiline mode")

    def compile_chips_call(self, tokens, line_number):
        """chips(name); を処理"""
        # tokens = [WORD "chips", BRACKET "(", WORD name, BRACKET ")", ...]
        if len(tokens) < 4:
            sws_error(line_number, "SyntaxError", "invalid chips call")
        
        name_token = tokens[2]
        if name_token.type != "WORD":
            sws_error(line_number, "SyntaxError", "chips call requires name")
        
        name = name_token.value
        
        if name not in self.chips:
            sws_error(line_number, "NameError", f"chips '{name}' is not declared yet")

        if name in self.recursion_stack:
            sws_error(line_number, "RecursionError", f"chips '{name}' has circular dependency")

        self.recursion_stack.add(name)
        try:
            # chips ブロックを再コンパイル
            for stmt_tokens, stmt_line in self.chips[name]:
                self.compile_statement(stmt_tokens, stmt_line)
        finally:
            self.recursion_stack.discard(name)

    def compile_lp(self, tokens, line_number):
        """lp(...) { ... } を処理"""
        sws_error(line_number, "SyntaxError", "lp not yet fully supported in multiline mode")

    def compile_tempoconst(self, tokens, line_number):
        """tempoconst = "120"; を処理"""
        # The statement builder removes the terminating semicolon.
        if len(tokens) != 3:
            sws_error(line_number, "SyntaxError", "tempoconst requires value")
        
        if tokens[1].type != "SYMBOL" or tokens[1].value != "=":
            sws_error(line_number, "SyntaxError", "tempoconst requires = operator")
        
        if tokens[2].type != "STRING":
            sws_error(line_number, "SyntaxError", "tempoconst value must be a string")
        
        value_str = tokens[2].value[1:-1]  # 引用符を除去
        
        self.tempoconst_count += 1
        if self.tempoconst_count > 1:
            sws_error(line_number, "ValueError", "tempoconst can only be set once")
        
        try:
            value = float(value_str)
        except ValueError:
            sws_error(line_number, "ValueError", "invalid tempo value (must be numeric)")

        if not math.isfinite(value):
            sws_error(line_number, "ValueError", "tempo must be finite")
        if value <= 0:
            sws_error(line_number, "ValueError", "tempo must be greater than 0")
        if value > 500:
            sws_error(line_number, "ValueError", "tempo is too high (max 500 BPM)")

        self.tempo_map = TempoMap(value)

    def compile_newtempo(self, tokens, line_number):
        """newtempo = "120"; を処理"""
        if len(tokens) != 3:
            sws_error(line_number, "SyntaxError", "newtempo requires value")
        
        if tokens[1].type != "SYMBOL" or tokens[1].value != "=":
            sws_error(line_number, "SyntaxError", "newtempo requires = operator")
        
        if tokens[2].type != "STRING":
            sws_error(line_number, "SyntaxError", "newtempo value must be a string")
        
        value_str = tokens[2].value[1:-1]
        
        try:
            value = float(value_str)
        except ValueError:
            sws_error(line_number, "ValueError", "invalid tempo value (must be numeric)")

        if not math.isfinite(value):
            sws_error(line_number, "ValueError", "tempo must be finite")
        if value <= 0:
            sws_error(line_number, "ValueError", "tempo must be greater than 0")
        if value > 500:
            sws_error(line_number, "ValueError", "tempo is too high (max 500 BPM)")

        self.tempo_map.set_tempo(self.main_cursor, value)

    def compile_key(self, tokens, line_number):
        """key = "C"; を処理"""
        if len(tokens) != 3:
            sws_error(line_number, "SyntaxError", "key requires value")
        
        if tokens[1].type != "SYMBOL" or tokens[1].value != "=":
            sws_error(line_number, "SyntaxError", "key requires = operator")
        
        if tokens[2].type != "STRING":
            sws_error(line_number, "SyntaxError", "key value must be a string")
        
        key_name = tokens[2].value[1:-1]

        if not key_name:
            sws_error(line_number, "ValueError", "key name cannot be empty")

        if key_name not in KEY_SCALES:
            sws_error(line_number, "ValueError", f"invalid key: {key_name}")

        self.key = key_name

    def compile_index_class(self, tokens, line_number):
        """index.class("name"); を処理"""
        if len(tokens) < 5:
            sws_error(line_number, "SyntaxError", "index.class requires value")
        
        # index . class ( "name" )
        if tokens[1].type != "SYMBOL" or tokens[1].value != ".":
            sws_error(line_number, "SyntaxError", "expected . after index")
        
        if tokens[2].type != "WORD" or tokens[2].value != "class":
            sws_error(line_number, "SyntaxError", "expected class after index.")
        
        if tokens[3].type != "BRACKET" or tokens[3].value != "(":
            sws_error(line_number, "SyntaxError", "expected ( after index.class")
        
        if tokens[4].type != "STRING":
            sws_error(line_number, "SyntaxError", "class name must be a string")
        
        class_name = tokens[4].value[1:-1]

        if not class_name:
            sws_error(line_number, "ValueError", "class name cannot be empty")

        self.current_ust_class = class_name

    def compile_output(self, tokens, line_number):
        """output.wav(...), output.midi(...), output.ust(...), output.ss(...) を処理"""
        # output . type ( "filename" )
        if len(tokens) < 5:
            sws_error(line_number, "SyntaxError", "output requires filename")
        
        if tokens[1].type != "SYMBOL" or tokens[1].value != ".":
            sws_error(line_number, "SyntaxError", "expected . after output")
        
        if tokens[2].type != "WORD":
            sws_error(line_number, "SyntaxError", "expected output type (wav/midi/ust/ss)")
        
        output_type = tokens[2].value.lower()
        
        if output_type not in ["wav", "midi", "ust", "ss"]:
            sws_error(line_number, "ValueError", f"unknown output type: {output_type}")
        
        if tokens[3].type != "BRACKET" or tokens[3].value != "(":
            sws_error(line_number, "SyntaxError", "expected ( after output type")
        
        if tokens[4].type != "STRING":
            sws_error(line_number, "SyntaxError", "filename must be a string")
        
        filename = tokens[4].value[1:-1]

        if not filename:
            sws_error(line_number, "ValueError", f"output.{output_type} requires a filename")

        req = OutputRequest(output_type, filename, line_number, self.current_ust_class if output_type == "ust" else None)
        self.output_requests.append(req)

    def compile_plugin(self, tokens, line_number):
        """plugin("name"); を処理"""
        if len(tokens) < 4:
            sws_error(line_number, "SyntaxError", "plugin requires name")
        
        if tokens[1].type != "BRACKET" or tokens[1].value != "(":
            sws_error(line_number, "SyntaxError", "expected ( after plugin")
        
        if tokens[2].type != "STRING":
            sws_error(line_number, "SyntaxError", "plugin name must be a string")
        
        plugin_name = tokens[2].value[1:-1]
        self.plugins_to_run.append((plugin_name, line_number))

    def compile_sleep(self, tokens, line_number):
        """sleep(4); を処理"""
        if len(tokens) < 4:
            sws_error(line_number, "SyntaxError", "sleep requires length")
        
        if tokens[1].type != "BRACKET" or tokens[1].value != "(":
            sws_error(line_number, "SyntaxError", "expected ( after sleep")
        
        if tokens[2].type != "WORD":
            sws_error(line_number, "SyntaxError", "sleep requires numeric length")
        
        length = tokens[2].value

        try:
            beats = length_to_beats(length)
        except ValueError as e:
            sws_error(line_number, "ValueError", str(e))

        self.main_cursor += beats

    def compile_snd(self, tokens, line_number):
        """snd(...); を処理"""
        if len(tokens) < 3:
            sws_error(line_number, "SyntaxError", "snd requires arguments")
        
        if tokens[1].type != "BRACKET" or tokens[1].value != "(":
            sws_error(line_number, "SyntaxError", "expected ( after snd")
        
        # () の中身をテキストに戻す
        paren_depth = 1
        args_tokens = []
        i = 2
        
        while i < len(tokens) and paren_depth > 0:
            if tokens[i].type == "BRACKET":
                if tokens[i].value == "(":
                    paren_depth += 1
                elif tokens[i].value == ")":
                    paren_depth -= 1
                    if paren_depth == 0:
                        break
            args_tokens.append(tokens[i])
            i += 1
        
        # args_tokens をテキストに変換
        args_text = self._tokens_to_text(args_tokens)
        
        try:
            args = split_arguments(args_text)
        except ValueError as e:
            sws_error(line_number, "SyntaxError", f"snd argument error: {str(e)}")

        if len(args) < 3:
            sws_error(line_number, "SyntaxError", "snd() requires at least 3 arguments (instrument, length, pitch)")

        self.compile_snd_args(line_number, args)

    def compile_snd_args(self, line_number, args):
        """snd の引数をコンパイル"""
        # instrument
        instrument_match = re.fullmatch(r'"([^"]+)"', args[0].strip())

        if not instrument_match:
            sws_error(line_number, "SyntaxError", 'instrument must be written as "name"')

        instrument = instrument_match.group(1).lower()

        if not instrument:
            sws_error(line_number, "ValueError", "instrument name cannot be empty")

        if instrument not in VALID_INSTRUMENTS:
            sws_error(line_number, "ValueError", f"unknown instrument: {instrument}")

        # duration
        duration = self._parse_duration_expression(args[1], line_number)

        # pitch
        pitch_arg = args[2].strip()
        if pitch_arg in self.variables or re.fullmatch(
            r"[A-Za-z_]\w*\s*\[.*\]",
            pitch_arg
        ):
            pitch_value = self._evaluate_expression(pitch_arg, line_number)
            if not isinstance(pitch_value, str):
                sws_error(line_number, "TypeError", "pitch variable must contain a note name")
            pitch_arg = pitch_value
        notes = []

        if pitch_arg == "null":
            notes = []
        elif pitch_arg.startswith("fsn="):
            value = pitch_arg[4:].strip()

            if not (value.startswith("[") and value.endswith("]")):
                sws_error(line_number, "SyntaxError", "invalid fsn (must be [note1,note2,...])")

            content = value[1:-1].strip()

            if not content:
                sws_error(line_number, "ValueError", "fsn cannot be empty")

            raw_notes = [x.strip() for x in content.split(",")]

            if len(raw_notes) > 128:
                sws_error(line_number, "ValueError", "fsn has too many notes (max 128)")

            for raw_note in raw_notes:
                if raw_note == "null":
                    sws_error(line_number, "ValueError", "null is not allowed inside fsn")
                note_obj = self.parse_note(raw_note, line_number)
                notes.append(note_obj)
        else:
            note_obj = self.parse_note(pitch_arg, line_number)
            notes.append(note_obj)

        # Parse attributes
        class_name = None
        lyric = None
        seen_attrs = set()

        for arg in args[3:]:
            if "=" not in arg:
                sws_error(line_number, "SyntaxError", f"invalid snd attribute: {arg}")

            attr_name, attr_value = arg.split("=", 1)
            attr_name = attr_name.strip()

            if not attr_name:
                sws_error(line_number, "SyntaxError", "attribute name cannot be empty")

            if attr_name in seen_attrs:
                sws_error(line_number, "SyntaxError", f"duplicate attribute: {attr_name}")

            seen_attrs.add(attr_name)

            if attr_name == "class":
                match = re.fullmatch(r'"([^"]*)"', attr_value.strip())
                if not match:
                    sws_error(line_number, "SyntaxError", 'class must be written as "name"')
                class_name = match.group(1)
                if not class_name:
                    sws_error(line_number, "ValueError", "class name cannot be empty")

            elif attr_name == "Lyric":
                match = re.fullmatch(r'"([^"]*)"', attr_value.strip())
                if not match:
                    sws_error(line_number, "SyntaxError", 'Lyric must be written as "text"')
                lyric = match.group(1)

            else:
                sws_error(line_number, "SyntaxError", f"unknown snd attribute: {attr_name}")

        # Apply lyric to all notes
        if lyric is not None:
            for note in notes:
                if isinstance(note, NoteData):
                    note.lyric = lyric

        # Validate pitch
        for note in notes:
            if note.pitch == "null":
                continue

            try:
                note_to_frequency(note.pitch, note.key, note.key_bypass)
            except ValueError as e:
                sws_error(line_number, "ValueError", str(e))

        # Determine start position based on class
        main_cursor_snapshot = self.main_cursor
        
        if class_name is not None:
            # Track-based: use track cursor if exists, otherwise initialize to main_cursor_snapshot
            if class_name not in self.track_cursors:
                self.track_cursors[class_name] = main_cursor_snapshot
            start = self.track_cursors[class_name]
        else:
            # No class: use main cursor
            start = self.main_cursor

        event = SoundEvent(instrument, start, duration, notes, line_number, class_name)
        self.events.append(event)

        # Update appropriate cursor
        if event.class_name is None:
            self.main_cursor = event.end
        else:
            self.track_cursors[event.class_name] = event.end

    def parse_note(self, raw_note, line_number):
        """単一の音符を解析"""

        note = raw_note
        slur = False
        key_bypass = False

        if note.endswith("~!") or note.endswith("!~"):
            slur = True
            key_bypass = True
            note = note[:-2]
        elif note.endswith("~"):
            slur = True
            note = note[:-1]
        elif note.endswith("!"):
            key_bypass = True
            note = note[:-1]

        if note != "null":
            try:
                note_to_midi(note, self.key, key_bypass)
            except ValueError as e:
                sws_error(line_number, "ValueError", str(e))

        return NoteData(note, slur, key_bypass, lyric=None, key=self.key)

    def _tokens_to_text(self, tokens):
        """トークン列をテキストに戻す"""
        result = []
        for token in tokens:
            if token.type == "STRING":
                result.append(token.value)
            elif token.type == "BRACKET":
                result.append(token.value)
            elif token.type == "SYMBOL":
                result.append(token.value)
            else:
                result.append(token.value)
        return " ".join(result)


# ============================================================
# SYNTH
# ============================================================

def envelope(t, duration):
    if duration <= 0:
        return 0.0

    attack = min(0.02, duration * 0.15)
    release = min(0.10, duration * 0.25)

    if t < attack:
        return t / attack

    if t > duration - release:
        return max(0.0, (duration - t) / release)

    return 1.0


def synth_wave(instrument, frequency, t):
    name = instrument.lower()

    if name in ("sine", "sin"):
        return math.sin(2 * math.pi * frequency * t)

    if name in ("square", "sq"):
        return 1.0 if math.sin(2 * math.pi * frequency * t) >= 0 else -1.0

    if name in ("triangle", "tri"):
        return 2 / math.pi * math.asin(math.sin(2 * math.pi * frequency * t))

    if name in ("saw", "sawtooth"):
        phase = (frequency * t) % 1.0
        return 2 * phase - 1

    if name in ("synth", "synth_lead"):
        return (
            math.sin(2 * math.pi * frequency * t)
            + 0.35 * math.sin(2 * math.pi * frequency * 2 * t)
        )

    if name in ("bass", "synth_bass"):
        return (
            math.sin(2 * math.pi * frequency * t)
            + 0.35 * math.sin(math.pi * frequency * t)
        )

    if name in ("piano", "grand_piano"):
        f = frequency
        return (
            math.sin(2 * math.pi * f * t)
            + 0.45 * math.sin(2 * math.pi * f * 2 * t)
            + 0.25 * math.sin(2 * math.pi * f * 3 * t)
            + 0.12 * math.sin(2 * math.pi * f * 4 * t)
        ) * math.exp(-1.8 * t)

    if name == "kick":
        f = frequency * (1 + 4 * math.exp(-25 * t))
        return math.sin(2 * math.pi * f * t) * math.exp(-10 * t)

    if name == "snare":
        return (
            (math.sin(2 * math.pi * 200 * t)
             + math.sin(2 * math.pi * 300 * t))
            * math.exp(-8 * t)
        )

    if name in ("hihat", "hi_hat"):
        return (
            (math.sin(2 * math.pi * 8000 * t)
             + math.sin(2 * math.pi * 12000 * t))
            * math.exp(-20 * t)
        )

    if name == "drum":
        f = frequency * (1 + 3 * math.exp(-20 * t))
        return math.sin(2 * math.pi * f * t) * math.exp(-8 * t)

    return math.sin(2 * math.pi * frequency * t)


# ============================================================
# SLUR ANALYSIS
# ============================================================

def analyze_slurs(events):
    """スラー対象を特定し、不正なスラーはエラーにする"""

    for i, event in enumerate(events):
        for note in event.notes:
            if isinstance(note, NoteData) and note.slur:
                found = False
                # search following events
                for j in range(i+1, len(events)):
                    next_event = events[j]
                    # same class/instrument may play overlapping; we only accept exact continuation
                    if not next_event.notes:
                        continue
                    # compare pitch on first note element of next_event (for single-note events)
                    next_note = next_event.notes[0]
                    if not isinstance(next_note, NoteData):
                        continue
                    if next_note.pitch != note.pitch:
                        continue
                    # check temporal adjacency
                    if abs(next_event.start - event.end) < 1e-9:
                        found = True
                        break
                    # allow same start (chordal slurs) only if next_event.start == event.start and next_event.end == event.end
                    if abs(next_event.start - event.start) < 1e-9 and abs(next_event.end - event.end) < 1e-9:
                        found = True
                        break
                    # if next_event starts after event.end, stop searching for continuation
                    if next_event.start > event.end + 1e-9:
                        break
                if not found:
                    raise ValueError(f"slur target not found for {note.pitch} at line {event.line}")


# ============================================================
# MIDI GENERATOR
# ============================================================

def write_variable_length(value):
    """MIDI variable length quantityを生成"""
    result = bytearray()
    result.append(value & 0x7F)
    value >>= 7
    
    while value:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    
    result.reverse()
    return bytes(result)


class MIDIGenerator:
    """MIDI形式ファイルを生成"""

    def __init__(self, events, tempo_map, key):
        self.events = events
        self.tempo_map = tempo_map
        self.key = key
        self.ppq = 480

    def generate(self, filename):
        """MIDIファイルを生成"""

        # イベントキュー（統合）
        event_queue = []

        # テンポイベント（priority=0）
        for seg_beat, tempo in self.tempo_map.segments:
            tick = int(seg_beat * self.ppq)
            microseconds_per_beat = int(60000000 / tempo)
            
            event = bytearray([
                0xFF, 0x51, 0x03,
                (microseconds_per_beat >> 16) & 0xFF,
                (microseconds_per_beat >> 8) & 0xFF,
                microseconds_per_beat & 0xFF
            ])
            
            event_queue.append((tick, 0, event))

        # ノートイベント
        for event in self.events:
            if not event.notes or event.notes[0].pitch == "null":
                continue

            start_tick = int(event.start * self.ppq)
            end_tick = int(event.end * self.ppq)

            for note in event.notes:
                if note.pitch == "null":
                    continue

                midi_note = note_to_midi(note.pitch, note.key, note.key_bypass)

                # Note On (priority=2)
                velocity = max(0, min(127, round(event.volume * 127 / 100)))
                note_on = bytearray([0x90, midi_note, velocity])
                event_queue.append((start_tick, 2, note_on))

                # Note Off (priority=1)
                note_off = bytearray([0x80, midi_note, 0])
                event_queue.append((end_tick, 1, note_off))

        # イベントをソート（tick順、同じtickならpriority順）
        event_queue.sort(key=lambda x: (x[0], x[1]))

        # トラックデータを生成
        track_data = bytearray()
        current_tick = 0

        for tick, priority, event in event_queue:
            delta = tick - current_tick
            track_data.extend(write_variable_length(delta))
            track_data.extend(event)
            current_tick = tick

        # End of Track
        track_data.extend(bytes([0x00, 0xFF, 0x2F, 0x00]))

        # ヘッダ
        header = bytearray([
            0x4D, 0x54, 0x68, 0x64,
            0x00, 0x00, 0x00, 0x06,
            0x00, 0x00,
            0x00, 0x01,
            (self.ppq >> 8) & 0xFF,
            self.ppq & 0xFF
        ])

        # トラックヘッダ
        track_header = bytearray([
            0x4D, 0x54, 0x72, 0x6B,
            (len(track_data) >> 24) & 0xFF,
            (len(track_data) >> 16) & 0xFF,
            (len(track_data) >> 8) & 0xFF,
            len(track_data) & 0xFF
        ])

        # 一時ファイルへ書き込み、成功時にreplace
        temp_fd, temp_path = tempfile.mkstemp(suffix='.mid')
        try:
            with os.fdopen(temp_fd, 'wb') as f:
                f.write(header)
                f.write(track_header)
                f.write(track_data)
                f.flush()
                os.fsync(f.fileno())
            
            for attempt in range(10):
                try:
                    os.replace(temp_path, filename)
                    break
                except (PermissionError, OSError):
                    if attempt >= 9:
                        raise
                    time.sleep(0.1)
        except Exception as e:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
            raise Exception(f"Failed to generate MIDI file: {str(e)}")


# ============================================================
# UST GENERATOR
# ============================================================

class USTGenerator:
    """UST形式ファイルを生成"""

    def __init__(self, events, tempo_map, key, class_filter=None):
        self.events = events
        self.tempo_map = tempo_map
        self.key = key
        self.class_filter = class_filter

    def generate(self, filename):
        """USTファイルを生成"""

        # クラスフィルタリング
        filtered_events = []
        if self.class_filter:
            for event in self.events:
                if event.class_name == self.class_filter:
                    filtered_events.append(event)
            
            if not filtered_events:
                raise ValueError(f"UST class '{self.class_filter}' not found")
        else:
            filtered_events = self.events

        # イベントを開始位置順にソート
        sorted_events = sorted(filtered_events, key=lambda e: (e.start, e.line))

        # USTヘッダ
        ust_lines = []
        ust_lines.append("[#VERSION]")
        ust_lines.append("UST Version1.2")
        ust_lines.append("")
        ust_lines.append("[#SETTING]")
        
        initial_tempo = 120.0
        if self.tempo_map.segments:
            initial_tempo = self.tempo_map.segments[0][1]
        
        ust_lines.append(f"Tempo={initial_tempo:.2f}")
        ust_lines.append("Tracks=1")
        ust_lines.append("ProjectName=SoundWavScript")
        ust_lines.append("VoiceDir=%VOICE%uta")
        ust_lines.append("OutFile=")
        ust_lines.append("CacheDir=sample.cache")
        ust_lines.append("Tool1=wavtool.exe")
        ust_lines.append("Tool2=resampler.exe")
        ust_lines.append("Mode2=True")
        ust_lines.append("")

        # タイムラインを構築
        note_index = 0
        current_beat = 0.0
        
        for event in sorted_events:
            # 空白部分を休符で埋める
            if event.start > current_beat:
                gap = event.start - current_beat
                gap_length = self.tempo_map.beat_to_ust_length(gap)
                
                ust_lines.append(f"[#{note_index:04d}]")
                ust_lines.append(f"Length={gap_length}")
                ust_lines.append(f"Lyric=R")
                ust_lines.append("Intensity=100")
                ust_lines.append("Modulation=0")
                ust_lines.append("")
                
                note_index += 1
                current_beat += gap

            # イベント処理
            if not event.notes or event.notes[0].pitch == "null":
                # 休符イベント
                ust_length = self.tempo_map.beat_to_ust_length(event.duration)
                
                ust_lines.append(f"[#{note_index:04d}]")
                ust_lines.append(f"Length={ust_length}")
                ust_lines.append(f"Lyric=R")
                ust_lines.append("Intensity=100")
                ust_lines.append("Modulation=0")
                ust_lines.append("")
                
                note_index += 1
                current_beat = event.end
                continue

            # 複数音は1ノートに
            ust_length = self.tempo_map.beat_to_ust_length(event.duration)

            # NoteNum：一番下の音
            midi_numbers = []
            for note in event.notes:
                if note.pitch != "null":
                    midi_num = note_to_midi(note.pitch, note.key, note.key_bypass)
                    midi_numbers.append(midi_num)
            
            if midi_numbers:
                note_num = min(midi_numbers)
            else:
                note_num = 60

            # Lyric
            if len(event.notes) > 1:
                # 複数音は低い順に音名連結
                note_pitches = []
                for midi_num in sorted(midi_numbers):
                    note_pitches.append(midi_to_note_name(midi_num))
                lyric = "".join(note_pitches)
            elif event.notes[0].lyric:
                lyric = event.notes[0].lyric
            else:
                lyric = "R"
            intensity = max(0, min(200, round(event.volume)))

            ust_lines.append(f"[#{note_index:04d}]")
            ust_lines.append(f"Length={ust_length}")
            ust_lines.append(f"Lyric={lyric}")
            ust_lines.append(f"NoteNum={note_num}")
            ust_lines.append(f"Intensity={intensity}")
            ust_lines.append("Modulation=0")
            ust_lines.append("")

            note_index += 1
            current_beat = event.end

        ust_lines.append("[#TRACKEND]")
        ust_lines.append("")

        # 一時ファイルへ書き込み、成功時にreplace
        temp_fd, temp_path = tempfile.mkstemp(suffix='.ust')
        try:
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                f.write("\n".join(ust_lines))
                f.flush()
                os.fsync(f.fileno())

            for attempt in range(10):
                try:
                    os.replace(temp_path, filename)
                    break
                except (PermissionError, OSError):
                    if attempt >= 9:
                        raise
                    time.sleep(0.1)
        except Exception as e:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
            raise Exception(f"Failed to generate UST file: {str(e)}")


# ============================================================
# SS GENERATOR
# ============================================================

class SSGenerator:
    """SWS .ss形式ファイルを生成"""

    def __init__(self, ss_source_code):
        self.ss_source_code = ss_source_code

    def generate(self, filename):
        """SSファイルを生成"""

        # 一時ファイルへ書き込み、成功時にreplace
        temp_fd, temp_path = tempfile.mkstemp(suffix='.ss')
        try:
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                f.write(self.ss_source_code)
                f.flush()
                os.fsync(f.fileno())

            for attempt in range(10):
                try:
                    os.replace(temp_path, filename)
                    break
                except (PermissionError, OSError):
                    if attempt >= 9:
                        raise
                    time.sleep(0.1)
        except Exception as e:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
            raise Exception(f"Failed to generate SS file: {str(e)}")


# ============================================================
# WAV RENDERER
# ============================================================

class Renderer:

    def __init__(self, events, tempo_map, key):
        self.events = events
        self.tempo_map = tempo_map
        self.key = key

    def render(self, filename):

        if not self.events:
            raise ValueError("no sound events")

        total_beats = max(event.end for event in self.events)

        if total_beats <= 0:
            raise ValueError("total duration is zero")

        total_seconds = self.tempo_map.beat_to_seconds(total_beats)

        total_samples = int(total_seconds * SAMPLE_RATE) + 1

        buffer = [0.0 for _ in range(total_samples)]

        for event in self.events:

            if not event.notes:
                continue

            start_seconds = self.tempo_map.beat_to_seconds(event.start)
            end_seconds = self.tempo_map.beat_to_seconds(event.end)

            duration_seconds = end_seconds - start_seconds

            if duration_seconds <= 0:
                continue

            start_sample = int(start_seconds * SAMPLE_RATE)
            count = int(duration_seconds * SAMPLE_RATE)
            volume = max(0.0, min(2.0, event.volume / 100.0))

            for note in event.notes:

                pitch = note.pitch if isinstance(note, NoteData) else note

                if pitch == "null":
                    continue

                frequency = note_to_frequency(pitch, note.key, note.key_bypass)

                for i in range(count):

                    index = start_sample + i

                    if index >= len(buffer):
                        break

                    t = i / SAMPLE_RATE

                    value = synth_wave(event.instrument, frequency, t)

                    value *= envelope(t, duration_seconds)

                    value *= 0.18 * volume

                    buffer[index] += value

        # Normalize
        peak = max((abs(x) for x in buffer), default=0.0)

        if peak > 0.95:
            scale = 0.95 / peak
            buffer = [x * scale for x in buffer]

        # 一時ファイルへ書き込み、成功時にreplace
        # Windows WinError 32対策：mkstemp() が開いたファイルハンドルを先に閉じる
        temp_fd, temp_path = tempfile.mkstemp(suffix='.wav')
        os.close(temp_fd)

        try:
            with wave.open(temp_path, "wb") as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(SAMPLE_WIDTH)
                wf.setframerate(SAMPLE_RATE)

                data = bytearray()

                for sample in buffer:
                    sample = max(-1.0, min(1.0, sample))
                    value = int(sample * 32767)
                    data.extend(struct.pack("<h", value))

                wf.writeframes(data)

            # wavファイルの書き込みが完全に完了してからreplace
            for attempt in range(10):
                try:
                    os.replace(temp_path, filename)
                    break
                except (PermissionError, OSError):
                    if attempt >= 9:
                        raise
                    time.sleep(0.1)
        except Exception as e:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
            raise Exception(f"Failed to generate WAV file: {str(e)}")


# ============================================================
# PLUGIN SYSTEM
# ============================================================

def load_plugin(plugin_name, line_number):
    """plugins/plugin_name.pyを動的読み込み"""

    if not re.fullmatch(r"[A-Za-z0-9_]+", plugin_name):
        sws_error(line_number, "ValueError", f"invalid plugin name: {plugin_name}")

    plugins_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "plugins"
    )

    plugin_path = os.path.join(plugins_dir, f"{plugin_name}.py")

    if not os.path.isfile(plugin_path):
        sws_error(line_number, "FileNotFoundError", f"plugin '{plugin_name}' not found at {plugin_path}")

    spec = importlib.util.spec_from_file_location(plugin_name, plugin_path)

    if spec is None or spec.loader is None:
        sws_error(line_number, "ImportError", f"plugin '{plugin_name}' failed to load")

    module = importlib.util.module_from_spec(spec)
    
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        sws_error(line_number, "RuntimeError", f"plugin '{plugin_name}' import error: {str(e)}")

    if not hasattr(module, "run"):
        sws_error(line_number, "AttributeError", f"plugin '{plugin_name}' does not have run() function")

    return module


def events_to_plugin_data(events, compiler):
    """イベントをPlugin API互換データに変換"""

    initial_tempo = 120.0
    if compiler.tempo_map.segments:
        initial_tempo = compiler.tempo_map.segments[0][1]

    data = {
        "sws_version": "0.2",
        "api_version": 1,
        "type": "song",
        "project": {
            "tempo": initial_tempo,
            "key": compiler.key
        },
        "events": [event.to_dict() for event in events]
    }

    return data


def run_plugins(plugin_list, events, compiler):
    """プラグインを実行（deep copyで独立性を保証）"""

    if not plugin_list:
        return

    for plugin_name, line_number in plugin_list:
        try:
            module = load_plugin(plugin_name, line_number)
            
            # deep copyしてプラグインに渡す（独立性を保証）
            data = events_to_plugin_data(events, compiler)
            data = copy.deepcopy(data)
            
            module.run(data)

        except SWSError as e:
            raise e

        except Exception as e:
            sws_error(line_number, "RuntimeError", f"plugin '{plugin_name}' failed: {str(e)}")


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def split_arguments(text):
    """括弧・括正確に解析してカンマで分割"""

    result = []
    current = ""

    bracket_depth = 0
    paren_depth = 0
    quote = False

    for i, char in enumerate(text):

        if char == '"' and (i == 0 or text[i-1] != '\\'):
            quote = not quote
            current += char
            continue

        if not quote:
            if char == "[":
                bracket_depth += 1
            elif char == "]":
                bracket_depth -= 1
                if bracket_depth < 0:
                    raise ValueError("unmatched ]")
            elif char == "(":
                paren_depth += 1
            elif char == ")":
                paren_depth -= 1
                if paren_depth < 0:
                    raise ValueError("unmatched )")

            if char == "," and bracket_depth == 0 and paren_depth == 0:
                result.append(current.strip())
                current = ""
                continue

        current += char

    if bracket_depth != 0:
        raise ValueError("unmatched [")
    if paren_depth != 0:
        raise ValueError("unmatched (")
    
    if current.strip():
        result.append(current.strip())

    return result


# ============================================================
# PLAYER
# ============================================================

def play_audio(filename):

    system = platform.system()

    try:

        if system == "Windows":
            import winsound
            winsound.PlaySound(filename, winsound.SND_FILENAME)
            return

        if system == "Darwin":
            subprocess.run(["afplay", filename], check=False)
            return

        if shutil.which("aplay"):
            subprocess.run(["aplay", filename], check=False)
            return

        if shutil.which("paplay"):
            subprocess.run(["paplay", filename], check=False)
            return

        if shutil.which("ffplay"):
            subprocess.run(["ffplay", "-nodisp", "-autoexit", filename], check=False)
            return

        cprint("warning: audio player not found.")

    except Exception as e:
        cprint(f"warning: playback error: {e}")


# ============================================================
# LOG
# ============================================================

def format_beats(beats):
    """ビート値を表示用に整形"""
    if beats == 1.0:
        return "1 beat"
    else:
        # strip trailing zeros
        return f"{beats:g} beat"


def format_pitch_for_log(notes):
    """イベントの音符を表示用にフォーマット"""

    if not notes:
        return "null"

    pitches = []
    for note in notes:
        if isinstance(note, NoteData):
            pitches.append(note.pitch)
        else:
            pitches.append(str(note))

    if len(pitches) == 1:
        return pitches[0]
    else:
        return "[" + ", ".join(pitches) + "]"


def print_success(event):
    """sound success ログ（解析成功のみ）"""

    pitch = format_pitch_for_log(event.notes)
    length = format_beats(event.duration)

    log_str = f"sound success:{event.line},{pitch},{length}"

    if event.class_name is not None:
        log_str += f",class={event.class_name}"
    else:
        log_str += ",class=main"

    cprint(log_str)


def print_output_success(request_type, output_path):
    """出力成功ログ（実際の保存成功時のみ）"""
    cprint(f"output success:{request_type},{output_path}")


# ============================================================
# COMPILATION PIPELINE
# ============================================================

def compile_and_run(filename):
    """ファイルをコンパイル・実行（.ss または .ust）"""

    try:
        compiler = Compiler()
        events = compiler.compile_file(filename)

    except SWSError as e:
        show_error(e.args[0])
        return False

    except Exception as e:
        cprint(f"compiler error: {e}")
        time.sleep(2)
        return False

    # Print success logs for compiled events
    for event in events:
        print_success(event)

    # Slur analysis
    try:
        analyze_slurs(events)
    except ValueError as e:
        sws_error(events[0].line if events else 1, "SlurError", str(e))
        show_error((events[0].line if events else 1, "SlurError", str(e)))
        return False

    # Plugin
    try:
        run_plugins(compiler.plugins_to_run, events, compiler)

    except SWSError as e:
        show_error(e.args[0])
        return False

    except Exception as e:
        cprint(f"plugin execution error: {e}")
        time.sleep(2)
        return False

    # Output Processing
    # 処理順序: SS → WAV → MIDI → UST → Playback
    has_ss_output = any(req.type == "ss" for req in compiler.output_requests)
    has_wav_output = any(req.type == "wav" for req in compiler.output_requests)
    has_midi_output = any(req.type == "midi" for req in compiler.output_requests)
    has_ust_output = any(req.type == "ust" for req in compiler.output_requests)

    wav_output_path = None

    # SS生成 (output.ss)
    if has_ss_output:
        try:
            ss_gen = SSGenerator(compiler.ss_source_code)

            for req in compiler.output_requests:
                if req.type == "ss":
                    output_path = req.get_output_path(filename)

                    cprint(f"generating: {output_path}")

                    # 親ディレクトリ作成
                    output_dir = os.path.dirname(output_path)
                    if output_dir and not os.path.exists(output_dir):
                        try:
                            os.makedirs(output_dir, exist_ok=True)
                        except Exception as e:
                            cprint(f"error: failed to create directory: {e}")
                            return False

                    ss_gen.generate(output_path)
                    print_output_success("ss", output_path)

        except Exception as e:
            cprint(f"SS generation error: {e}")
            time.sleep(2)
            return False

    # WAV生成 (output.wav)
    if has_wav_output:
        try:
            renderer = Renderer(events, compiler.tempo_map, compiler.key)

            for req in compiler.output_requests:
                if req.type == "wav":
                    output_path = req.get_output_path(filename)

                    cprint(f"rendering: {output_path}")

                    # 親ディレクトリ作成
                    output_dir = os.path.dirname(output_path)
                    if output_dir and not os.path.exists(output_dir):
                        try:
                            os.makedirs(output_dir, exist_ok=True)
                        except Exception as e:
                            cprint(f"error: failed to create directory: {e}")
                            return False

                    renderer.render(output_path)
                    print_output_success("wav", output_path)
                    wav_output_path = output_path

        except Exception as e:
            cprint(f"WAV render error: {e}")
            time.sleep(2)
            return False

    # MIDI生成 (output.midi)
    if has_midi_output:
        try:
            for req in compiler.output_requests:
                if req.type == "midi":
                    output_path = req.get_output_path(filename)

                    cprint(f"generating: {output_path}")

                    # 親ディレクトリ作成
                    output_dir = os.path.dirname(output_path)
                    if output_dir and not os.path.exists(output_dir):
                        try:
                            os.makedirs(output_dir, exist_ok=True)
                        except Exception as e:
                            cprint(f"error: failed to create directory: {e}")
                            return False

                    midi_gen = MIDIGenerator(events, compiler.tempo_map, compiler.key)
                    midi_gen.generate(output_path)
                    print_output_success("midi", output_path)

        except Exception as e:
            cprint(f"MIDI generation error: {e}")
            time.sleep(2)
            return False

    # UST生成 (output.ust)
    if has_ust_output:
        try:
            for req in compiler.output_requests:
                if req.type == "ust":
                    output_path = req.get_output_path(filename)

                    cprint(f"generating: {output_path}")

                    # 親ディレクトリ作成
                    output_dir = os.path.dirname(output_path)
                    if output_dir and not os.path.exists(output_dir):
                        try:
                            os.makedirs(output_dir, exist_ok=True)
                        except Exception as e:
                            cprint(f"error: failed to create directory: {e}")
                            return False

                    ust_gen = USTGenerator(events, compiler.tempo_map, compiler.key, req.class_name)
                    ust_gen.generate(output_path)
                    print_output_success("ust", output_path)

        except Exception as e:
            cprint(f"UST generation error: {e}")
            time.sleep(2)
            return False

    # Generate the documented default WAV when no output.wav was requested.
    if wav_output_path is None:
        try:
            renderer = Renderer(events, compiler.tempo_map, compiler.key)
            wav_output_path = os.path.splitext(filename)[0] + ".wav"
            output_dir = os.path.dirname(wav_output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)
            cprint(f"rendering: {wav_output_path}")
            renderer.render(wav_output_path)
            print_output_success("wav", wav_output_path)
        except Exception as e:
            cprint(f"default WAV render error: {e}")
            time.sleep(2)
            return False

    # Playback after all requested/default output has been rendered.
    if wav_output_path and os.path.exists(wav_output_path):
        cprint("playing...")
        play_audio(wav_output_path)

    cprint("sound complete.")

    return True


# ============================================================
# INTERACTIVE CONSOLE - Terminal Commands (not .ss commands)
# ============================================================

def interactive_console():
    """対話型コンソール"""

    cprint("==============================")
    cprint(" Sound Wav Script v0.2")
    cprint(" Interactive Console")
    cprint("==============================")
    cprint("")
    cprint("Terminal Commands:")
    cprint("  color RRGGBB  - Set console color (e.g. color FF0000)")
    cprint("  color rainbow - Rainbow mode")
    cprint("  run filename  - Compile and run .ss, .ust, .mid or .midi file")
    cprint("  help          - Show this help")
    cprint("  exit          - Exit")
    cprint("")

    while True:
        try:
            user_input = input("SWS> ").strip()

            if not user_input:
                continue

            # Parse command
            parts = user_input.split(maxsplit=1)
            command = parts[0].lower()

            if command == "exit":
                cprint("Exiting SWS.")
                break

            elif command == "help":
                cprint("Terminal Commands:")
                cprint("  color RRGGBB  - Set console color (e.g. color FF0000)")
                cprint("  color rainbow - Rainbow mode")
                cprint("  run filename  - Compile and run .ss, .ust, .mid or .midi file")
                cprint("  help          - Show this help")
                cprint("  exit          - Exit")

            elif command == "color":
                if len(parts) < 2:
                    cprint("error: color requires a value (RRGGBB or 'rainbow')")
                    continue
                color_value = parts[1]
                set_console_color(color_value)

            elif command == "run":
                if len(parts) < 2:
                    cprint("error: run requires a filename")
                    continue
                filename = parts[1]
                if os.path.isfile(filename):
                    compile_and_run(filename)
                else:
                    cprint(f"error: file not found: {filename}")

            else:
                cprint(f"error: unknown command: {command}")
                cprint("type 'help' for available commands")

        except KeyboardInterrupt:
            cprint("\nExiting SWS.")
            break
        except Exception as e:
            cprint(f"error: {e}")


# ============================================================
# MAIN
# ============================================================

def main():

    if len(sys.argv) >= 2:
        # Direct file execution
        filename = sys.argv[1]

        if not os.path.isfile(filename):
            cprint(f"error: file not found: {filename}")
            return 1

        ext = os.path.splitext(filename)[1].lower()
        if ext not in [".ss", ".ust", ".mid", ".midi"]:
            cprint(f"error: unsupported file format: {ext}")
            return 1

        cprint("==============================")
        cprint(" Sound Wav Script v0.2")
        cprint("==============================")

        if compile_and_run(filename):
            return 0
        else:
            return 1

    else:
        # Interactive console
        interactive_console()
        return 0


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":

    try:
        sys.exit(main())

    except KeyboardInterrupt:
        cprint("\nSWS stopped.")
        sys.exit(130)

    except Exception as e:
        # Top-level catch to improve double-click debugability
        cprint("SWS fatal error:")
        cprint(str(e))
        try:
            input("Press Enter to exit...")
        except Exception:
            pass
        sys.exit(1)