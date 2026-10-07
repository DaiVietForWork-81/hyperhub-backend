/**
 * D:\Project\Bot\cpp_core\cpp_bridge.js
 * High-Performance Node.js <-> C++ Native Engine Bridge.
 * 
 * Connects Node.js directly to native_core.dll using Koffi FFI (Zero-Copy C-ABI).
 * Sub-microsecond execution speed, 100% Deterministic.
 */

import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';
import koffi from 'koffi';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Tìm file DLL đã biên dịch
const dllPaths = [
    path.join(__dirname, 'native_core.dll'),
    path.join(__dirname, '..', '..', 'Bot', 'cpp_core', 'native_core.dll'),
    path.resolve('D:/Project/Bot/cpp_core/native_core.dll'),
];

let dllPath = null;
for (const p of dllPaths) {
    if (fs.existsSync(p)) {
        dllPath = p;
        break;
    }
}

if (!dllPath) {
    throw new Error(`[CPPCore] Không tìm thấy file native_core.dll tại: ${dllPaths.join(', ')}`);
}

// Nạp thư viện C++ DLL
const lib = koffi.load(dllPath);

// Đăng ký các hàm C-ABI
const c_calculate_shannon_entropy = lib.func('double calculate_shannon_entropy(str text, int len)');
const c_fast_levenshtein_similarity = lib.func('double fast_levenshtein_similarity(str s1, int len1, str s2, int len2)');
const c_fast_clean_think_tags = lib.func('int fast_clean_think_tags(str text, int len, _Out_ uint8_t *out_buf, int out_buf_size)');
const c_fast_dedup_consecutive_words = lib.func('int fast_dedup_consecutive_words(str text, int len, _Out_ uint8_t *out_buf, int out_buf_size)');
const c_fast_token_compare = lib.func('int fast_token_compare(str actual, int actual_len, str expected, int expected_len, double float_epsilon, _Out_ uint8_t *error_buf, int error_buf_size)');
const c_fast_code_metrics = lib.func('void fast_code_metrics(str code, int len, _Out_ int *out_lines, _Out_ int *out_comment_lines, _Out_ int *out_blank_lines, _Out_ double *out_entropy)');
const c_fast_sha256 = lib.func('void fast_sha256(_In_ uint8_t *data, int len, _Out_ uint8_t *out_hex, int out_hex_size)');
const c_fast_detect_magic_bytes = lib.func('int fast_detect_magic_bytes(_In_ uint8_t *data, int len, _Out_ uint8_t *out_type, int out_type_size)');

export class CPPCore {
    /**
     * Đo mức độ ngẫu nhiên/hỗn loạn của chuỗi ký tự (Shannon Entropy).
     * @param {string} text 
     * @returns {number}
     */
    static calculateShannonEntropy(text) {
        if (!text || typeof text !== 'string') return 0.0;
        return c_calculate_shannon_entropy(text, Buffer.byteLength(text));
    }

    /**
     * Tính toán tỷ lệ tương đồng chuỗi Levenshtein (từ 0.0 đến 1.0).
     * Thuật toán quy hoạch động 2 dòng O(min(N, M)) trong C++.
     * @param {string} s1 
     * @param {string} s2 
     * @returns {number}
     */
    static fastLevenshteinSimilarity(s1, s2) {
        if (!s1 || !s2) return 0.0;
        return c_fast_levenshtein_similarity(s1, Buffer.byteLength(s1), s2, Buffer.byteLength(s2));
    }

    /**
     * Lọc bỏ toàn bộ thẻ suy luận <think>...</think> của LLM trong duy nhất 1 lần duyệt O(N).
     * @param {string} text 
     * @returns {string}
     */
    static fastCleanThinkTags(text) {
        if (!text || typeof text !== 'string') return '';
        const len = Buffer.byteLength(text);
        const buf = Buffer.alloc(len + 64);
        const outLen = c_fast_clean_think_tags(text, len, buf, buf.length);
        return buf.toString('utf8', 0, outLen);
    }

    /**
     * Khử lặp từ liên tiếp do hiện tượng lắp bắp của mô hình ngôn ngữ Tiếng Việt.
     * @param {string} text 
     * @returns {string}
     */
    static fastDedupConsecutiveWords(text) {
        if (!text || typeof text !== 'string') return '';
        const len = Buffer.byteLength(text);
        const buf = Buffer.alloc(len + 64);
        const outLen = c_fast_dedup_consecutive_words(text, len, buf, buf.length);
        return buf.toString('utf8', 0, outLen);
    }

    /**
     * So khớp token đầu ra chấm bài thi lập trình với hỗ trợ epsilon cho số thực.
     * @param {string} actual 
     * @param {string} expected 
     * @param {number} floatEpsilon 
     * @returns {{ code: number, accepted: boolean, message: string }}
     */
    static fastTokenCompare(actual, expected, floatEpsilon = 1e-6) {
        const actBufLen = Buffer.byteLength(actual || '');
        const expBufLen = Buffer.byteLength(expected || '');
        const errBuf = Buffer.alloc(512);

        const code = c_fast_token_compare(
            actual || '',
            actBufLen,
            expected || '',
            expBufLen,
            floatEpsilon,
            errBuf,
            errBuf.length
        );

        const message = errBuf.toString('utf8').replace(/\0.*$/, '').trim();
        return {
            code,
            accepted: code === 0,
            message: message || (code === 0 ? 'Accepted' : 'Mismatch'),
        };
    }

    /**
     * Trích xuất các chỉ số mã nguồn (Code Metrics) trong 1 lần duyệt O(N).
     * @param {string} code 
     * @returns {{ lines: number, commentLines: number, blankLines: number, entropy: number }}
     */
    static fastCodeMetrics(code) {
        if (!code || typeof code !== 'string') {
            return { lines: 0, commentLines: 0, blankLines: 0, entropy: 0.0 };
        }
        const lines = [0];
        const comments = [0];
        const blanks = [0];
        const entropy = [0.0];

        c_fast_code_metrics(code, Buffer.byteLength(code), lines, comments, blanks, entropy);

        return {
            lines: lines[0],
            commentLines: comments[0],
            blankLines: blanks[0],
            entropy: entropy[0],
        };
    }

    /**
     * Tính SHA-256 hash của buffer nhị phân thuần C++.
     * @param {Buffer | Uint8Array} data 
     * @returns {string} Chuỗi hex 64 ký tự
     */
    static fastSha256(data) {
        if (!data || !data.length) return '';
        const buf = Buffer.isBuffer(data) ? data : Buffer.from(data);
        const outHex = Buffer.alloc(65);
        c_fast_sha256(buf, buf.length, outHex, outHex.length);
        return outHex.toString('ascii', 0, 64);
    }

    /**
     * Nhận dạng loại file qua Magic Bytes header thuần C++.
     * @param {Buffer | Uint8Array} data 
     * @returns {string} e.g. "PDF", "DOCX", "ZIP", "PNG", "JPEG", "UNKNOWN"
     */
    static fastDetectMagicBytes(data) {
        if (!data || data.length < 4) return 'UNKNOWN';
        const buf = Buffer.isBuffer(data) ? data : Buffer.from(data);
        const outType = Buffer.alloc(32);
        const ret = c_fast_detect_magic_bytes(buf, buf.length, outType, outType.length);
        return ret > 0 ? outType.toString('ascii').replace(/\0.*$/, '').trim() : 'UNKNOWN';
    }
}

export default CPPCore;
