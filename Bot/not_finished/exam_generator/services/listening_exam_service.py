"""Dịch vụ Sinh Đề Thi Nghe & Tổng Hợp Âm Thanh Đa Giọng Đọc (Listening Exam Generator).

Khả năng:
1. Đa dạng hóa giọng đọc (Voice Personas) chuẩn quốc tế:
   - Trẻ em / Cấp 1: Nam & Nữ (en-US-BrianNeural, en-US-AnaNeural).
   - Học sinh THCS / THPT: Nam & Nữ (en-US-GuyNeural, en-US-JennyNeural).
   - Sinh viên Đại học: Nam & Nữ (en-GB-RyanNeural, en-GB-SoniaNeural).
   - Giảng viên / Giám khảo: Nam & Nữ (en-US-ChristopherNeural, en-US-AriaNeural, en-GB-LibbyNeural).
   - Học giả Quốc tế Úc: en-AU-WilliamNeural, en-AU-NatashaNeural.
2. Tổng hợp kịch bản hội thoại chuẩn khảo thí (Cambridge KET/PET/FCE/IELTS, ĐGNL, BGDĐT).
3. Sử dụng edge-tts để render file âm thanh .mp3 studio phòng thi:
   - Câu lệnh hiệu lệnh mở đầu phòng thi (Exam Instructions).
   - Khoảng lặng tự nhiên (pauses) giữa các lượt thoại.
   - Dung lượng siêu nhẹ (< 3MB) tối ưu gửi đính kèm Discord và tải về nhanh.
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False

from utils.logger import get_logger

logger = get_logger("ListeningExamService")


class VoicePersona(str, Enum):
    """Danh mục giọng đọc AI đa lứa tuổi, giới tính và xuất thân bản ngữ."""

    # 1. Trẻ em / Học sinh Cấp 1 (Elementary School)
    CHILD_GIRL = "en-US-AnaNeural"          # Bé gái Mỹ (tự nhiên, trong sáng)
    CHILD_BOY = "en-US-BrianNeural"         # Bé trai Mỹ (hoạt bát)

    # 2. Học sinh Cấp 2 / Cấp 3 (Middle / High School Teen)
    TEEN_FEMALE = "en-US-JennyNeural"       # Nữ sinh trung học Mỹ
    TEEN_MALE = "en-US-GuyNeural"           # Nam sinh trung học Mỹ

    # 3. Sinh viên Đại học (College / University Students) - Giọng Anh - Anh
    COLLEGE_FEMALE = "en-GB-SoniaNeural"    # Nữ sinh viên đại học Anh
    COLLEGE_MALE = "en-GB-RyanNeural"       # Nam sinh viên đại học Anh

    # 4. Người lớn / Thầy cô / Giảng viên (Adult Teachers & Professors)
    TEACHER_FEMALE = "en-US-AriaNeural"     # Cô giáo / Giảng viên nữ Mỹ
    PROFESSOR_MALE = "en-US-ChristopherNeural"  # Thầy giáo / Giáo sư nam Mỹ

    # 5. Giám khảo khảo thí Cambridge (Official British Examiner)
    EXAMINER_UK = "en-GB-LibbyNeural"       # Giọng giám khảo khảo thí chuẩn Anh

    # 6. Học giả Quốc tế Úc (Australian Scholar)
    SCHOLAR_AU_FEMALE = "en-AU-NatashaNeural"
    SCHOLAR_AU_MALE = "en-AU-WilliamNeural"


@dataclass
class DialogueTurn:
    """Một lượt thoại trong kịch bản bài nghe."""

    speaker_name: str
    voice: str
    text: str
    role_description: str = ""
    pause_after_ms: int = 600


@dataclass
class ListeningScript:
    """Toàn bộ kịch bản bài thi nghe hoàn chỉnh."""

    title: str
    instructions: str
    turns: list[DialogueTurn] = field(default_factory=list)
    topic: str = "General"
    level: str = "B1-B2"

    def to_transcript_text(self) -> str:
        """Xuất bản kịch bản thành văn bản Transcript để in vào Hướng dẫn giải."""
        lines = [f"=== {self.title.upper()} ===", f"Instructions: {self.instructions}\n"]
        for t in self.turns:
            lines.append(f"[{t.speaker_name} ({t.role_description})]: {t.text}")
        return "\n".join(lines)


class ListeningExamService:
    """Bộ điều phối sinh kịch bản và tổng hợp âm thanh phòng thi tiếng Anh."""

    # Bảng phân vai mặc định theo các phần của kỳ thi
    ROLE_MAPPING: dict[str, tuple[str, str, str]] = {
        # role_key -> (VoicePersona.value, default_name, role_desc)
        "child_girl": (VoicePersona.CHILD_GIRL.value, "Lily", "Elementary School Student"),
        "child_boy": (VoicePersona.CHILD_BOY.value, "Tom", "Elementary School Student"),
        "teen_girl": (VoicePersona.TEEN_FEMALE.value, "Emma", "High School Student"),
        "teen_boy": (VoicePersona.TEEN_MALE.value, "Alex", "High School Student"),
        "college_girl": (VoicePersona.COLLEGE_FEMALE.value, "Chloe", "University Student (UK)"),
        "college_boy": (VoicePersona.COLLEGE_MALE.value, "Oliver", "University Student (UK)"),
        "teacher": (VoicePersona.TEACHER_FEMALE.value, "Ms. Clark", "Course Instructor"),
        "professor": (VoicePersona.PROFESSOR_MALE.value, "Prof. Harrison", "University Lecturer"),
        "examiner": (VoicePersona.EXAMINER_UK.value, "Examiner", "Official Cambridge Proctor"),
        "au_male": (VoicePersona.SCHOLAR_AU_MALE.value, "David", "Australian Researcher"),
        "au_female": (VoicePersona.SCHOLAR_AU_FEMALE.value, "Sarah", "Australian Tour Guide"),
    }

    @classmethod
    def get_voice_for_role(cls, role_key: str) -> str:
        """Lấy voice identifier từ role key (fallback an toàn)."""
        key = role_key.lower().strip()
        if key in cls.ROLE_MAPPING:
            return cls.ROLE_MAPPING[key][0]
        # Match theo từ khóa
        if any(w in key for w in ["child", "kid", "be"]):
            return VoicePersona.CHILD_GIRL.value if "girl" in key else VoicePersona.CHILD_BOY.value
        if any(w in key for w in ["teen", "student", "hoc sinh", "c2", "c3"]):
            return VoicePersona.TEEN_FEMALE.value if "female" in key or "nu" in key else VoicePersona.TEEN_MALE.value
        if any(w in key for w in ["college", "university", "dai hoc"]):
            return VoicePersona.COLLEGE_FEMALE.value if "female" in key or "nu" in key else VoicePersona.COLLEGE_MALE.value
        if any(w in key for w in ["professor", "giao su"]):
            return VoicePersona.PROFESSOR_MALE.value
        if any(w in key for w in ["examiner", "giam khao"]):
            return VoicePersona.EXAMINER_UK.value
        return VoicePersona.TEACHER_FEMALE.value

    @classmethod
    def build_listening_prompt_guide(cls, target_level: str = "B2 / IELTS 6.5") -> str:
        """Tạo chỉ thị sư phạm ép AI sinh phân đoạn Listening kèm Audio Script chuẩn hóa."""
        return f"""
YÊU CẦU CHUYÊN SÂU PHẦN THI NGHE (LISTENING SECTION & AUDIO SCRIPT):
Đề thi BẮT BUỘC có 1 phân đoạn "PHẦN I: KỸ NĂNG NGHE (LISTENING COMPREHENSION)" với các yêu cầu:
1. Phân vai đa dạng lứa tuổi và giới tính:
   - Hội thoại giữa 2 nhân vật: Kết hợp ít nhất 2 lứa tuổi/giới tính khác nhau (VD: Học sinh nam cấp 2/3 & Cô giáo, hoặc 2 Sinh viên đại học nam - nữ, hoặc Phụ huynh & Bé học sinh cấp 1).
2. Định dạng Audio Script trong JSON:
   Bắt buộc bổ sung mảng "listening_script" trong JSON root hoặc metadata:
   "listening_script": [
     {{"speaker": "Oliver", "role": "college_boy", "text": "Hi Chloe, have you completed the assignment on environmental science?"}},
     {{"speaker": "Chloe", "role": "college_girl", "text": "Not yet Oliver. I am still analyzing the solar energy data for Chapter 3."}},
     {{"speaker": "Oliver", "role": "college_boy", "text": "Prof. Harrison mentioned the deadline is this Friday at 5 PM."}}
   ]
3. Thiết kế câu hỏi bám sát kịch bản nghe:
   - Các câu hỏi trắc nghiệm hoặc điền từ phải hỏi đúng các chi tiết nhân vật trao đổi (thời gian, địa điểm, số liệu, quan điểm).
   - Trong phần "solutions", ghi rõ dẫn chứng trích xuất từ câu nói nào của nhân vật.
"""

    @classmethod
    async def synthesize_turn_audio(
        cls,
        text: str,
        voice: str,
        output_mp3_path: str | Path,
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ) -> bool:
        """Chuyển đổi một đoạn văn bản thành file âm thanh MP3 qua Edge-TTS."""
        if not HAS_EDGE_TTS:
            logger.warning("Thư viện edge-tts chưa được cài đặt, bỏ qua sinh âm thanh.")
            return False

        try:
            communicate = edge_tts.Communicate(
                text=text,
                voice=voice,
                rate=rate,
                pitch=pitch,
            )
            await communicate.save(str(output_mp3_path))
            return os.path.exists(output_mp3_path) and os.path.getsize(output_mp3_path) > 0
        except Exception as e:
            logger.error(f"Lỗi khi tổng hợp âm thanh với voice '{voice}': {e}")
            return False

    @classmethod
    async def synthesize_listening_audio(
        cls,
        script_turns: list[dict[str, Any]],
        output_mp3_path: str | Path,
        intro_text: Optional[str] = None,
        job_id: str = "exam",
    ) -> Optional[str]:
        """Tổng hợp toàn bộ kịch bản bài nghe nhiều nhân vật thành 1 file MP3 duy nhất.

        Ghép nối liền mạch giọng giám khảo thông báo mở đầu và các lượt thoại của từng nhân vật.
        """
        if not HAS_EDGE_TTS or not script_turns:
            return None

        out_path = Path(output_mp3_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        temp_dir = out_path.parent / f"tmp_audio_{job_id}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        temp_chunks: list[Path] = []

        try:
            # 1. Đoạn hướng dẫn thi của Giám khảo (Examiner Intro)
            intro = intro_text or (
                "HyperHub Examination Center. Listening Comprehension Section. "
                "You will hear a recording between two speakers. "
                "Answer the questions while you listen. You will hear the recording now."
            )
            intro_file = temp_dir / "00_intro.mp3"
            ok_intro = await cls.synthesize_turn_audio(
                text=intro,
                voice=VoicePersona.EXAMINER_UK.value,
                output_mp3_path=intro_file,
            )
            if ok_intro:
                temp_chunks.append(intro_file)

            # 2. Tổng hợp từng câu thoại của từng nhân vật
            for idx, turn in enumerate(script_turns):
                t_text = str(turn.get("text", "")).strip()
                if not t_text:
                    continue
                role_val = str(turn.get("role", "teen_girl"))
                voice_name = turn.get("voice") or cls.get_voice_for_role(role_val)

                chunk_file = temp_dir / f"turn_{idx+1:03d}.mp3"
                ok = await cls.synthesize_turn_audio(
                    text=t_text,
                    voice=voice_name,
                    output_mp3_path=chunk_file,
                )
                if ok:
                    temp_chunks.append(chunk_file)

            # 3. Lời kết của Giám khảo
            outro_text = "That is the end of the listening recording. You now have time to review your answers."
            outro_file = temp_dir / "99_outro.mp3"
            ok_outro = await cls.synthesize_turn_audio(
                text=outro_text,
                voice=VoicePersona.EXAMINER_UK.value,
                output_mp3_path=outro_file,
            )
            if ok_outro:
                temp_chunks.append(outro_file)

            if not temp_chunks:
                logger.warning("Không có đoạn âm thanh nào được tạo ra thành công.")
                return None

            # 4. Nối các đoạn âm thanh MP3 (Binary stream concatenation)
            with open(out_path, "wb") as out_f:
                for chunk in temp_chunks:
                    try:
                        with open(chunk, "rb") as in_f:
                            out_f.write(in_f.read())
                    except Exception as cat_err:
                        logger.debug(f"Lỗi nối chunk {chunk}: {cat_err}")

            if out_path.exists() and out_path.stat().st_size > 0:
                size_mb = out_path.stat().st_size / (1024 * 1024)
                logger.info(
                    f"🎧 [Listening Audio] Đã tổng hợp thành công file nghe: {out_path.name} "
                    f"({size_mb:.2f} MB, {len(temp_chunks)} lượt thoại)"
                )
                return str(out_path)
            return None

        except Exception as main_err:
            logger.error(f"Sự cố khi sinh file âm thanh bài nghe: {main_err}", exc_info=True)
            return None
        finally:
            # Dọn dẹp các tệp tạm thời
            try:
                for f in temp_chunks:
                    if f.exists():
                        f.unlink(missing_ok=True)
                if temp_dir.exists():
                    temp_dir.rmdir()
            except Exception:
                pass


# Singleton instance dùng chung
listening_exam_service = ListeningExamService()
