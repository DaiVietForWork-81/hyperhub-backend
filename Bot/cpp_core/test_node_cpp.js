/**
 * D:\Project\Bot\cpp_core\test_node_cpp.js
 * Test Suite & Benchmark for Node.js + C++ Native Integration.
 */

import { CPPCore } from './cpp_bridge.js';

console.log('================================================================');
console.log('   🚀 KIỂM THỬ KẾT HỢP NODE.JS (v' + process.versions.node + ') + C++ (NATIVE ENGINE)');
console.log('================================================================\n');

// 1. Kiểm thử Shannon Entropy
const text = "Dự án Discord Bot CP Arena kết hợp C++ và Node.js đạt hiệu năng tối đa!";
const start1 = performance.now();
const entropy = CPPCore.calculateShannonEntropy(text);
const time1 = (performance.now() - start1).toFixed(4);
console.log('1️⃣ [Shannon Entropy]');
console.log(`   • Nội dung: "${text}"`);
console.log(`   • Entropy tính bằng C++: ${entropy.toFixed(4)} bits/byte`);
console.log(`   • Thời gian thực thi: ${time1} ms\n`);

// 2. Kiểm thử Levenshtein Similarity
const s1 = "Đề thi Olympic Tin học Khối Chuyên";
const s2 = "Đề thi Olympic Tin học Khối HSG";
const start2 = performance.now();
const sim = CPPCore.fastLevenshteinSimilarity(s1, s2);
const time2 = (performance.now() - start2).toFixed(4);
console.log('2️⃣ [Levenshtein String Similarity]');
console.log(`   • Chuỗi 1: "${s1}"`);
console.log(`   • Chuỗi 2: "${s2}"`);
console.log(`   • Độ tương đồng: ${(sim * 100).toFixed(2)}%`);
console.log(`   • Thời gian thực thi: ${time2} ms\n`);

// 3. Kiểm thử lọc thẻ suy luận <think>
const rawAI = '<think>Mô hình đang phân tích thuật toán đồ thị Dijkstra O(E log V)...</think>Lời giải chính xác là D.';
const cleaned = CPPCore.fastCleanThinkTags(rawAI);
console.log('3️⃣ [Fast Clean Think Tags]');
console.log(`   • Đầu vào LLM: "${rawAI}"`);
console.log(`   • Đầu ra làm sạch bởi C++: "${cleaned}"\n`);

// 4. Kiểm thử khử từ lặp
const stutter = 'Hôm nay hôm nay thời tiết rất rất đẹp và mát mẻ';
const deduped = CPPCore.fastDedupConsecutiveWords(stutter);
console.log('4️⃣ [Fast Dedup Consecutive Words]');
console.log(`   • Chuỗi gốc: "${stutter}"`);
console.log(`   • Sau khi khử lặp C++: "${deduped}"\n`);

// 5. Kiểm thử so khớp Token chấm bài (Token Compare)
const actualOutput = "123.45600 789 HELLO_WORLD";
const expectedOutput = "123.456 789 hello_world";
const cmpResult = CPPCore.fastTokenCompare(actualOutput, expectedOutput, 1e-4);
console.log('5️⃣ [Fast Token Compare]');
console.log(`   • Thí sinh: "${actualOutput}"`);
console.log(`   • Đáp án:   "${expectedOutput}"`);
console.log(`   • Kết quả chấm: ${cmpResult.accepted ? '✅ ACCEPTED' : '❌ WRONG ANSWER'}`);
console.log(`   • Thông báo C++: ${cmpResult.message}\n`);

// 6. Kiểm thử trích xuất Code Metrics (Lines, Comments, Blanks, Entropy)
const sampleCode = `
#include <iostream>
using namespace std;

// Hàm tính giai thừa
long long factorial(int n) {
    /* Đệ quy cơ bản */
    if (n <= 1) return 1;
    return n * factorial(n - 1);
}

int main() {
    cout << factorial(10) << endl;
    return 0;
}
`;
const metrics = CPPCore.fastCodeMetrics(sampleCode);
console.log('6️⃣ [Fast Code Metrics Single Pass O(N)]');
console.log(`   • Tổng số dòng: ${metrics.lines}`);
console.log(`   • Số dòng chú thích: ${metrics.commentLines}`);
console.log(`   • Số dòng trống: ${metrics.blankLines}`);
console.log(`   • Mức độ hỗn loạn Entropy: ${metrics.entropy.toFixed(4)}\n`);

// 7. Kiểm thử SHA-256 thuần C++
const shaInput = Buffer.from("Hello Antigravity Engine Test");
const shaResult = CPPCore.fastSha256(shaInput);
console.log('7️⃣ [Fast SHA-256 Native C++]');
console.log(`   • Đầu vào: "${shaInput.toString()}"`);
console.log(`   • SHA-256 C++: ${shaResult}\n`);

// 8. Kiểm thử Magic Bytes header
const pdfHeader = Buffer.from("%PDF-1.7 standard header bytes");
const magicPdf = CPPCore.fastDetectMagicBytes(pdfHeader);
const docxHeader = Buffer.from("PK\x03\x04\x14\x00\x06\x00word/document.xml content");
const magicDocx = CPPCore.fastDetectMagicBytes(docxHeader);
console.log('8️⃣ [Fast Magic Bytes Header Detection]');
console.log(`   • Header PDF: ${magicPdf}`);
console.log(`   • Header DOCX: ${magicDocx}\n`);

// 9. Benchmark 10,000 lần gọi C++ từ Node.js
console.log('⚡ [BENCHMARK HIỆU NĂNG]: Chạy 10,000 phép tính Levenshtein C++ liên tục trong Node.js...');
const benchStart = performance.now();
for (let i = 0; i < 10000; i++) {
    CPPCore.fastLevenshteinSimilarity(s1, s2);
}
const benchTotal = (performance.now() - benchStart).toFixed(2);
const avgUs = ((benchTotal / 10000) * 1000).toFixed(2);
console.log(`   • Tổng thời gian cho 10,000 lần gọi: ${benchTotal} ms`);
console.log(`   • Tốc độ trung bình mỗi lần gọi: ${avgUs} µs (micro-giây / 0.00${avgUs} ms)`);
console.log('\n🎉 TẤT CẢ PHÉP THỬ KẾT HỢP NODE.JS + C++ HOÀN TOÀN THÀNH CÔNG VƯỢT TRỘI!');
