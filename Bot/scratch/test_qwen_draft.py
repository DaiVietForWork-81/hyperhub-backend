import urllib.request, json, time

draft_prompt = """Hãy thiết kế một bộ đề thi hoàn chỉnh và hướng dẫn chấm:
- Môn học: IELTS Academic 8.0 (Reading & Writing)
- Quy mô: Ngắn (4 câu Reading trắc nghiệm + 1 Task 2 Writing tự luận)
- Mã đề: HH-8001
- Thời gian: 45 phút

Trả về DUY NHẤT JSON theo cấu trúc:
{
  "metadata": {"exam_title": "IELTS ACADEMIC PRACTICE TEST", "subject": "IELTS Academic 8.0", "exam_code": "HH-8001", "duration": "45 phút"},
  "questions": [
    {"type": "section_header", "title": "READING PASSAGE AND QUESTIONS"},
    {"type": "question", "number": "1", "points": "1.0", "text": "According to paragraph 1...", "options": ["A. ...", "B. ...", "C. ...", "D. ..."], "has_diagram": false}
  ],
  "solutions": [
    {"number": "1", "is_multiple_choice": true, "correct_key": "A", "explanation": "Paragraph 1 states...", "rubric": [["Correct key", 1.0]]}
  ]
}
Chỉ trả về JSON.
"""

payload = {
    'model': 'qwen2.5:3b',
    'prompt': draft_prompt,
    'stream': False,
    'options': {'temperature': 0.3, 'num_gpu': 0, 'num_thread': 4, 'num_ctx': 2048}
}

t0 = time.time()
req = urllib.request.Request('http://127.0.0.1:11434/api/generate', data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
with urllib.request.urlopen(req, timeout=300) as res:
    data = json.loads(res.read().decode())
    print(f'Done in {time.time()-t0:.1f}s')
    resp = data.get('response', '')
    print('Length:', len(resp))
    print(resp[:400])
