"""Kiểm thử tự động cho ListeningExamService (Sinh bài nghe & tổng hợp giọng nói)."""

import os
import tempfile
import pytest

try:
    from not_finished.exam_generator.services.listening_exam_service import (
        DialogueTurn,
        ListeningScript,
        VoicePersona,
        listening_exam_service,
    )
except ImportError:
    from services.listening_exam_service import (
        DialogueTurn,
        ListeningScript,
        VoicePersona,
        listening_exam_service,
    )


def test_voice_persona_role_mapping():
    """Kiểm tra ánh xạ vai nhân vật sang giọng đọc Edge-TTS tương ứng."""
    assert listening_exam_service.get_voice_for_role("child_girl") == VoicePersona.CHILD_GIRL.value
    assert listening_exam_service.get_voice_for_role("child_boy") == VoicePersona.CHILD_BOY.value
    assert listening_exam_service.get_voice_for_role("teen_girl") == VoicePersona.TEEN_FEMALE.value
    assert listening_exam_service.get_voice_for_role("teen_boy") == VoicePersona.TEEN_MALE.value
    assert listening_exam_service.get_voice_for_role("college_girl") == VoicePersona.COLLEGE_FEMALE.value
    assert listening_exam_service.get_voice_for_role("college_boy") == VoicePersona.COLLEGE_MALE.value
    assert listening_exam_service.get_voice_for_role("examiner") == VoicePersona.EXAMINER_UK.value
    assert listening_exam_service.get_voice_for_role("au_male") == VoicePersona.SCHOLAR_AU_MALE.value


def test_voice_fallback_heuristics():
    """Kiểm tra cơ chế suy đoán giọng đọc tự động khi role không có trong từ điển chuẩn."""
    # Trẻ em
    assert listening_exam_service.get_voice_for_role("kid_girl") == VoicePersona.CHILD_GIRL.value
    assert listening_exam_service.get_voice_for_role("be trai") == VoicePersona.CHILD_BOY.value

    # Học sinh
    assert listening_exam_service.get_voice_for_role("hoc sinh c3") == VoicePersona.TEEN_MALE.value

    # Giáo sư & Giám khảo
    assert listening_exam_service.get_voice_for_role("giao su toan") == VoicePersona.PROFESSOR_MALE.value
    assert listening_exam_service.get_voice_for_role("giam khao ielts") == VoicePersona.EXAMINER_UK.value

    # Default fallback
    assert listening_exam_service.get_voice_for_role("unknown_person") == VoicePersona.TEACHER_FEMALE.value


def test_build_listening_prompt_guide():
    """Kiểm tra chỉ thị prompt hướng dẫn AI tạo phân đoạn nghe."""
    guide = listening_exam_service.build_listening_prompt_guide(target_level="IELTS 7.0")
    assert "LISTENING COMPREHENSION" in guide
    assert "listening_script" in guide
    assert "speaker" in guide


def test_listening_script_to_transcript():
    """Kiểm tra xuất transcript văn bản in ấn từ kịch bản nghe."""
    script = ListeningScript(
        title="Part 1: University Campus Discussion",
        instructions="Listen to the conversation and answer questions 1 to 4.",
        turns=[
            DialogueTurn(speaker_name="Oliver", voice="en-GB-RyanNeural", text="Hello Chloe, are you ready?", role_description="College Boy"),
            DialogueTurn(speaker_name="Chloe", voice="en-GB-SoniaNeural", text="Yes, let's head to the library.", role_description="College Girl"),
        ],
    )
    transcript = script.to_transcript_text()
    assert "PART 1: UNIVERSITY CAMPUS DISCUSSION" in transcript
    assert "Oliver (College Boy)" in transcript
    assert "Chloe (College Girl)" in transcript
    assert "Hello Chloe, are you ready?" in transcript


@pytest.mark.asyncio
async def test_synthesize_listening_audio_pipeline():
    """Kiểm tra quá trình tổng hợp âm thanh MP3 hoàn chỉnh với edge-tts."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_mp3 = os.path.join(tmp_dir, "test_exam_listening.mp3")

        script_turns = [
            {"speaker": "Lily", "role": "child_girl", "text": "Good morning teacher!"},
            {"speaker": "Ms. Clark", "role": "teacher", "text": "Good morning Lily, welcome to the science class."},
        ]

        result_path = await listening_exam_service.synthesize_listening_audio(
            script_turns=script_turns,
            output_mp3_path=out_mp3,
            intro_text="Welcome to the listening test.",
            job_id="test_job",
        )

        assert result_path is not None
        assert os.path.exists(result_path)
        assert os.path.getsize(result_path) > 1000  # MP3 có dung lượng hợp lệ
