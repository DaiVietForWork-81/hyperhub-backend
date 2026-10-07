/**
 * D:\Project\Bot\cpp_core\cpp_bridge.d.ts
 * TypeScript Type Definitions for CPPCore Node.js Bridge.
 */

export interface TokenCompareResult {
    code: number;
    accepted: boolean;
    message: string;
}

export interface CodeMetricsResult {
    lines: number;
    commentLines: number;
    blankLines: number;
    entropy: number;
}

export declare class CPPCore {
    /**
     * Đo mức độ hỗn loạn/ngẫu nhiên của chuỗi văn bản (Shannon Entropy).
     */
    static calculateShannonEntropy(text: string): number;

    /**
     * Tính toán tỷ lệ tương đồng chuỗi Levenshtein (từ 0.0 đến 1.0).
     */
    static fastLevenshteinSimilarity(s1: string, s2: string): number;

    /**
     * Lọc bỏ toàn bộ thẻ suy luận <think>...</think> của LLM trong 1 lần duyệt O(N).
     */
    static fastCleanThinkTags(text: string): string;

    /**
     * Khử lặp từ liên tiếp do hiện tượng lắp bắp của mô hình Tiếng Việt.
     */
    static fastDedupConsecutiveWords(text: string): string;

    /**
     * So khớp token đầu ra chấm bài thi lập trình với hỗ trợ epsilon cho số thực.
     */
    static fastTokenCompare(
        actual: string,
        expected: string,
        floatEpsilon?: number
    ): TokenCompareResult;

    /**
     * Trích xuất các chỉ số mã nguồn (Code Metrics) trong 1 lần duyệt O(N).
     */
    static fastCodeMetrics(code: string): CodeMetricsResult;

    /**
     * Tính SHA-256 hash của buffer nhị phân thuần C++.
     */
    static fastSha256(data: Buffer | Uint8Array): string;

    /**
     * Nhận dạng loại file qua Magic Bytes header thuần C++.
     */
    static fastDetectMagicBytes(data: Buffer | Uint8Array): string;
}

export default CPPCore;
