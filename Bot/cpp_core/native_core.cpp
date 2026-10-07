/**
 * cpp_core/native_core.cpp
 * C++ Native Acceleration Engine for Discord CP Bot & AI Heuristics.
 * 
 * Provides high-performance, zero-allocation algorithms:
 * 1. calculate_shannon_entropy: O(N) Shannon entropy calculation for code text.
 * 2. fast_code_metrics: Single-pass line counting, comment density, and entropy extraction.
 * 3. fast_token_compare: Zero-copy token-by-token comparison with floating-point epsilon matching.
 * 4. fast_levenshtein_similarity: Two-row DP string edit distance and similarity ratio calculation.
 * 
 * Exported as standard C-ABI (extern "C") to be loaded via Python ctypes.
 */

#include <cmath>
#include <cctype>
#include <cstring>
#include <cstdlib>
#include <vector>
#include <string>
#include <string_view>
#include <algorithm>
#include <cstdio>
#include <cstdint>

#if defined(_WIN32) || defined(__WIN32__) || defined(WIN32)
#define NATIVE_EXPORT __declspec(dllexport)
#else
#define NATIVE_EXPORT __attribute__((visibility("default")))
#endif

extern "C" {

/**
 * Tính toán Shannon Entropy của chuỗi ký tự (đo mức độ hỗn loạn của mã nguồn).
 * Công thức: H = - sum(p_i * log2(p_i)) với p_i là tần suất xuất hiện của ký tự i.
 */
NATIVE_EXPORT double calculate_shannon_entropy(const char* text, int len) {
    if (!text || len <= 0) {
        return 0.0;
    }

    // Đếm tần suất xuất hiện của các byte (0 - 255)
    unsigned int freq[256] = {0};
    int counted = 0;

    for (int i = 0; i < len; ++i) {
        unsigned char c = static_cast<unsigned char>(text[i]);
        // Bỏ qua ký tự xuống dòng / carriage return để tính entropy nội dung thực tế
        if (c != '\r' && c != '\n') {
            freq[c]++;
            counted++;
        }
    }

    if (counted == 0) {
        return 0.0;
    }

    double entropy = 0.0;
    const double inv_counted = 1.0 / static_cast<double>(counted);
    const double inv_log2 = 1.4426950408889634; // 1.0 / ln(2)

    for (int i = 0; i < 256; ++i) {
        if (freq[i] > 0) {
            double p = static_cast<double>(freq[i]) * inv_counted;
            entropy -= p * std::log(p) * inv_log2;
        }
    }

    return entropy;
}

/**
 * Trích xuất các chỉ số mã nguồn (Code Metrics) trong duy nhất 1 lần duyệt (Single Pass O(N)):
 * - Tổng số dòng (lines)
 * - Số dòng chú thích (comment lines: bắt đầu bằng #, //, /*, *)
 * - Số dòng trống (blank lines)
 * - Shannon entropy của mã nguồn
 */
NATIVE_EXPORT void fast_code_metrics(
    const char* code,
    int len,
    int* out_lines,
    int* out_comment_lines,
    int* out_blank_lines,
    double* out_entropy
) {
    if (!code || len <= 0) {
        if (out_lines) *out_lines = 0;
        if (out_comment_lines) *out_comment_lines = 0;
        if (out_blank_lines) *out_blank_lines = 0;
        if (out_entropy) *out_entropy = 0.0;
        return;
    }

    int lines = 0;
    int comment_lines = 0;
    int blank_lines = 0;

    unsigned int freq[256] = {0};
    int counted = 0;

    int line_start = 0;
    while (line_start < len) {
        // Tìm vị trí kết thúc dòng
        int line_end = line_start;
        while (line_end < len && code[line_end] != '\n') {
            line_end++;
        }

        lines++;

        // Bỏ qua khoảng trắng đầu dòng
        int first_non_ws = line_start;
        while (first_non_ws < line_end && std::isspace(static_cast<unsigned char>(code[first_non_ws]))) {
            first_non_ws++;
        }

        if (first_non_ws >= line_end) {
            blank_lines++;
        } else {
            // Kiểm tra xem dòng có phải là comment không
            char c1 = code[first_non_ws];
            char c2 = (first_non_ws + 1 < line_end) ? code[first_non_ws + 1] : '\0';

            if (c1 == '#' || (c1 == '/' && c2 == '/') || (c1 == '/' && c2 == '*') || c1 == '*') {
                comment_lines++;
            }
        }

        // Cập nhật tần suất ký tự cho Shannon entropy
        for (int i = line_start; i < line_end; ++i) {
            unsigned char c = static_cast<unsigned char>(code[i]);
            if (c != '\r') {
                freq[c]++;
                counted++;
            }
        }

        // Chuyển sang dòng tiếp theo
        line_start = line_end + 1;
    }

    double entropy = 0.0;
    if (counted > 0) {
        const double inv_counted = 1.0 / static_cast<double>(counted);
        const double inv_log2 = 1.4426950408889634;
        for (int i = 0; i < 256; ++i) {
            if (freq[i] > 0) {
                double p = static_cast<double>(freq[i]) * inv_counted;
                entropy -= p * std::log(p) * inv_log2;
            }
        }
    }

    if (out_lines) *out_lines = lines;
    if (out_comment_lines) *out_comment_lines = comment_lines;
    if (out_blank_lines) *out_blank_lines = blank_lines;
    if (out_entropy) *out_entropy = entropy;
}

/**
 * Trình so khớp token tốc độ cao (Fast Token Comparator) với con trỏ thô (Zero-Copy):
 * - Bỏ qua khoảng trắng / ký tự xuống dòng tùy ý giữa các token.
 * - So sánh trực tiếp chuỗi token hoặc parse số thực theo sai số epsilon cho phép.
 * - Mã trả về:
 *     0: Trùng khớp chính xác (Accepted)
 *     1: Sai số lượng token (Token Count Mismatch)
 *     2: Sai số thực vượt quá sai số epsilon (Float Mismatch)
 *     3: Token chuỗi không khớp (String Token Mismatch)
 * - Ghi thông điệp chẩn đoán chi tiết bằng Tiếng Việt vào error_buf.
 */
NATIVE_EXPORT int fast_token_compare(
    const char* actual,
    int actual_len,
    const char* expected,
    int expected_len,
    double float_epsilon,
    char* error_buf,
    int error_buf_size
) {
    if (!error_buf || error_buf_size <= 0) {
        return -1;
    }
    error_buf[0] = '\0';

    int act_pos = 0;
    int exp_pos = 0;
    int token_index = 0;

    auto next_token = [](const char* str, int len, int& pos, int& tok_start, int& tok_len) -> bool {
        while (pos < len && std::isspace(static_cast<unsigned char>(str[pos]))) {
            pos++;
        }
        if (pos >= len) {
            return false;
        }
        tok_start = pos;
        while (pos < len && !std::isspace(static_cast<unsigned char>(str[pos]))) {
            pos++;
        }
        tok_len = pos - tok_start;
        return true;
    };

    while (true) {
        int a_start = 0, a_len = 0;
        int e_start = 0, e_len = 0;

        bool has_a = next_token(actual, actual_len, act_pos, a_start, a_len);
        bool has_e = next_token(expected, expected_len, exp_pos, e_start, e_len);

        if (!has_a && !has_e) {
            // Cả 2 chuỗi đều kết thúc và khớp toàn bộ tokens
            std::snprintf(error_buf, error_buf_size, "Toàn bộ kết quả đầu ra đều khớp chính xác.");
            return 0;
        }

        if (has_a != has_e) {
            token_index++;
            if (!has_a) {
                std::snprintf(
                    error_buf,
                    error_buf_size,
                    "Thiếu dữ liệu đầu ra: Nhận được ít hơn số lượng giá trị kỳ vọng (dừng tại token #%d).",
                    token_index
                );
            } else {
                std::snprintf(
                    error_buf,
                    error_buf_size,
                    "Thừa dữ liệu đầu ra: Nhận được nhiều hơn số lượng giá trị kỳ vọng (thừa từ token #%d).",
                    token_index
                );
            }
            return 1;
        }

        token_index++;

        // 1. So khớp chuỗi chính xác
        bool str_match = (a_len == e_len) && (std::memcmp(actual + a_start, expected + e_start, a_len) == 0);
        if (str_match) {
            continue;
        }

        // 2. Thử so sánh số thực
        char a_sub[128];
        char e_sub[128];
        int copy_a = std::min(a_len, 127);
        int copy_e = std::min(e_len, 127);
        std::memcpy(a_sub, actual + a_start, copy_a);
        a_sub[copy_a] = '\0';
        std::memcpy(e_sub, expected + e_start, copy_e);
        e_sub[copy_e] = '\0';

        char* end_a = nullptr;
        char* end_e = nullptr;
        double val_a = std::strtod(a_sub, &end_a);
        double val_e = std::strtod(e_sub, &end_e);

        if (end_a == a_sub + a_len && end_e == e_sub + e_len) {
            // Cả hai đều là số thực hợp lệ
            double diff = std::fabs(val_a - val_e);
            double denom = std::max(1.0, std::fabs(val_e));
            if (diff / denom <= float_epsilon) {
                continue; // Khớp trong sai số cho phép
            } else {
                std::snprintf(
                    error_buf,
                    error_buf_size,
                    "Sai số thực tại token #%d: Kỳ vọng `%.6g`, nhận được `%.6g` (Độ lệch: %.6g > %.6g).",
                    token_index,
                    val_e,
                    val_a,
                    diff,
                    float_epsilon
                );
                return 2;
            }
        }

        // Không khớp chuỗi và không phải số thực tương thích
        std::snprintf(
            error_buf,
            error_buf_size,
            "Giá trị không khớp tại token #%d: Kỳ vọng `%s`, nhận được `%s`.",
            token_index,
            e_sub,
            a_sub
        );
        return 3;
    }
}

/**
 * Tính toán độ tương đồng Levenshtein Distance (tỷ lệ 0.0 -> 1.0) với bộ nhớ O(M).
 * Dùng cho kiểm tra mã tương đồng / trùng lặp / chống đạo văn giữa các submission.
 */
NATIVE_EXPORT double fast_levenshtein_similarity(
    const char* s1,
    int len1,
    const char* s2,
    int len2
) {
    if (!s1 || !s2) return 0.0;
    if (len1 == 0 && len2 == 0) return 1.0;
    if (len1 == 0 || len2 == 0) return 0.0;

    // Giảm độ dài nếu vượt quá ngưỡng tối đa để tối ưu thời gian phản hồi
    const int MAX_COMPARE_LEN = 4096;
    if (len1 > MAX_COMPARE_LEN) len1 = MAX_COMPARE_LEN;
    if (len2 > MAX_COMPARE_LEN) len2 = MAX_COMPARE_LEN;

    if (len1 == len2 && std::memcmp(s1, s2, len1) == 0) {
        return 1.0;
    }

    // Luôn chọn s2 là chuỗi ngắn hơn để tối ưu bộ nhớ O(min(len1, len2))
    if (len1 < len2) {
        std::swap(s1, s2);
        std::swap(len1, len2);
    }

    std::vector<int> prev_row(len2 + 1);
    std::vector<int> curr_row(len2 + 1);

    for (int j = 0; j <= len2; ++j) {
        prev_row[j] = j;
    }

    for (int i = 1; i <= len1; ++i) {
        curr_row[0] = i;
        char c1 = s1[i - 1];

        for (int j = 1; j <= len2; ++j) {
            char c2 = s2[j - 1];
            int cost = (c1 == c2) ? 0 : 1;
            curr_row[j] = std::min({
                prev_row[j] + 1,       // Deletion
                curr_row[j - 1] + 1,   // Insertion
                prev_row[j - 1] + cost // Substitution
            });
        }
        prev_row = curr_row;
    }

    int distance = prev_row[len2];
    int max_len = std::max(len1, len2);
    if (max_len == 0) return 1.0;

    double sim = 1.0 - (static_cast<double>(distance) / static_cast<double>(max_len));
    return std::max(0.0, std::min(1.0, sim));
}

/**
 * Lọc bỏ toàn bộ khối suy luận <think>...</think> của mô hình AI trong duy nhất 1 lần duyệt O(N).
 */
NATIVE_EXPORT int fast_clean_think_tags(
    const char* text,
    int len,
    char* out_buf,
    int out_buf_size
) {
    if (!text || len <= 0 || !out_buf || out_buf_size <= 0) {
        if (out_buf && out_buf_size > 0) out_buf[0] = '\0';
        return 0;
    }

    int in_pos = 0;
    int out_pos = 0;
    bool in_think = false;

    auto match_ci = [](const char* src, const char* target, int t_len) -> bool {
        for (int i = 0; i < t_len; ++i) {
            if (std::tolower(static_cast<unsigned char>(src[i])) != std::tolower(static_cast<unsigned char>(target[i]))) {
                return false;
            }
        }
        return true;
    };

    while (in_pos < len && out_pos < out_buf_size - 1) {
        if (!in_think) {
            if (in_pos + 7 <= len && match_ci(text + in_pos, "<think>", 7)) {
                in_think = true;
                in_pos += 7;
                continue;
            }
            // Bỏ qua thẻ đóng </think> lẻ loi nếu model sinh ra không có thẻ mở
            if (in_pos + 8 <= len && match_ci(text + in_pos, "</think>", 8)) {
                in_pos += 8;
                continue;
            }
            // Bỏ qua các thẻ biến dạng rác như </>
            if (in_pos + 3 <= len && text[in_pos] == '<' && text[in_pos + 1] == '/' && text[in_pos + 2] == '>') {
                in_pos += 3;
                continue;
            }
            out_buf[out_pos++] = text[in_pos++];
        } else {
            if (in_pos + 8 <= len && match_ci(text + in_pos, "</think>", 8)) {
                in_think = false;
                in_pos += 8;
                continue;
            }
            in_pos++;
        }
    }
    out_buf[out_pos] = '\0';
    return out_pos;
}

/**
 * Khử lặp từ liên tiếp (Consecutive Word Deduplication) để chống hiện tượng nói lắp của LLM tiếng Việt.
 * Thay thế 5 vòng lặp regex nặng nề trong Python bằng duyệt con trỏ thô O(N) trong C++.
 */
NATIVE_EXPORT int fast_dedup_consecutive_words(
    const char* text,
    int len,
    char* out_buf,
    int out_buf_size
) {
    if (!text || len <= 0 || !out_buf || out_buf_size <= 0) {
        if (out_buf && out_buf_size > 0) out_buf[0] = '\0';
        return 0;
    }

    int in_pos = 0;
    int out_pos = 0;
    char last_word[128] = {0};
    int last_word_len = 0;

    auto is_word_char = [](char c) -> bool {
        return std::isalnum(static_cast<unsigned char>(c)) || static_cast<unsigned char>(c) > 127;
    };

    while (in_pos < len && out_pos < out_buf_size - 1) {
        // Sao chép các ký tự không phải chữ (khoảng trắng, dấu câu)
        if (!is_word_char(text[in_pos])) {
            out_buf[out_pos++] = text[in_pos++];
            continue;
        }

        // Đọc 1 từ
        int w_start = in_pos;
        while (in_pos < len && is_word_char(text[in_pos])) {
            in_pos++;
        }
        int w_len = in_pos - w_start;

        // So sánh với từ liền trước (case-insensitive)
        bool is_dup = false;
        if (w_len == last_word_len && w_len > 0 && w_len < 128) {
            is_dup = true;
            for (int k = 0; k < w_len; ++k) {
                if (std::tolower(static_cast<unsigned char>(text[w_start + k])) !=
                    std::tolower(static_cast<unsigned char>(last_word[k]))) {
                    is_dup = false;
                    break;
                }
            }
        }

        if (!is_dup) {
            // Ghi từ vào output
            int to_copy = std::min(w_len, out_buf_size - 1 - out_pos);
            std::memcpy(out_buf + out_pos, text + w_start, to_copy);
            out_pos += to_copy;

            // Cập nhật last_word
            int copy_last = std::min(w_len, 127);
            std::memcpy(last_word, text + w_start, copy_last);
            last_word[copy_last] = '\0';
            last_word_len = copy_last;
        } else {
            // Bỏ qua từ lặp: lùi lại xóa khoảng trắng thừa trước đó nếu cần
            while (out_pos > 0 && (out_buf[out_pos - 1] == ' ' || out_buf[out_pos - 1] == '\t')) {
                out_pos--;
            }
        }
    }

    out_buf[out_pos] = '\0';
    return out_pos;
}

/**
 * Trích xuất và làm sạch khối JSON {...} từ output LLM trong C++:
 * - Tự động định vị ngoặc mở { đầu tiên và ngoặc đóng } cuối cùng
 * - Xóa dấu phẩy thừa trước } và ]
 */
NATIVE_EXPORT int fast_extract_json_block(
    const char* text,
    int len,
    char* out_buf,
    int out_buf_size
) {
    if (!text || len <= 0 || !out_buf || out_buf_size <= 0) {
        if (out_buf && out_buf_size > 0) out_buf[0] = '\0';
        return 0;
    }

    // 1. Tìm vị trí dấu { đầu tiên
    int start_pos = -1;
    for (int i = 0; i < len; ++i) {
        if (text[i] == '{') {
            start_pos = i;
            break;
        }
    }
    if (start_pos == -1) {
        out_buf[0] = '\0';
        return 0;
    }

    // 2. Tìm vị trí dấu } cuối cùng
    int end_pos = -1;
    for (int i = len - 1; i >= start_pos; --i) {
        if (text[i] == '}') {
            end_pos = i;
            break;
        }
    }
    if (end_pos == -1 || end_pos < start_pos) {
        out_buf[0] = '\0';
        return 0;
    }

    // 3. Sao chép và làm sạch: bỏ dấu phẩy thừa trước } hoặc ]
    int out_pos = 0;
    for (int i = start_pos; i <= end_pos && out_pos < out_buf_size - 1; ++i) {
        char c = text[i];
        if (c == ',') {
            // Nhìn trước xem ký tự không khoảng trắng tiếp theo có phải } hoặc ]
            int next_k = i + 1;
            while (next_k <= end_pos && std::isspace(static_cast<unsigned char>(text[next_k]))) {
                next_k++;
            }
            if (next_k <= end_pos && (text[next_k] == '}' || text[next_k] == ']')) {
                continue; // Bỏ qua dấu phẩy thừa
            }
        }
        out_buf[out_pos++] = c;
    }

    out_buf[out_pos] = '\0';
    return out_pos;
}

/**
 * SHA-256 thuần C++ (không cần OpenSSL) - Dùng cho Duplicate Detection.
 * Trả về chuỗi hex 64 ký tự vào out_hex.
 */
NATIVE_EXPORT void fast_sha256(const unsigned char* data, int len, char* out_hex, int out_hex_size) {
    if (!data || len <= 0 || !out_hex || out_hex_size < 65) {
        if (out_hex && out_hex_size > 0) out_hex[0] = '\0';
        return;
    }

    // SHA-256 constants
    static const uint32_t K[64] = {
        0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
        0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
        0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
        0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
        0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
        0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
        0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
        0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
    };

    auto rotr = [](uint32_t x, int n) -> uint32_t { return (x >> n) | (x << (32 - n)); };
    auto ch = [](uint32_t x, uint32_t y, uint32_t z) -> uint32_t { return (x & y) ^ (~x & z); };
    auto maj = [](uint32_t x, uint32_t y, uint32_t z) -> uint32_t { return (x & y) ^ (x & z) ^ (y & z); };
    auto sig0 = [&rotr](uint32_t x) -> uint32_t { return rotr(x, 2) ^ rotr(x, 13) ^ rotr(x, 22); };
    auto sig1 = [&rotr](uint32_t x) -> uint32_t { return rotr(x, 6) ^ rotr(x, 11) ^ rotr(x, 25); };
    auto ssig0 = [&rotr](uint32_t x) -> uint32_t { return rotr(x, 7) ^ rotr(x, 18) ^ (x >> 3); };
    auto ssig1 = [&rotr](uint32_t x) -> uint32_t { return rotr(x, 17) ^ rotr(x, 19) ^ (x >> 10); };

    uint32_t h[8] = {
        0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
        0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19
    };

    // Pre-processing: padding
    uint64_t bit_len = (uint64_t)len * 8;
    int padded_len = ((len + 8) / 64 + 1) * 64;
    std::vector<unsigned char> msg(padded_len, 0);
    std::memcpy(msg.data(), data, len);
    msg[len] = 0x80;
    for (int i = 0; i < 8; ++i) {
        msg[padded_len - 1 - i] = (unsigned char)(bit_len >> (i * 8));
    }

    // Process each 64-byte block
    for (int offset = 0; offset < padded_len; offset += 64) {
        uint32_t w[64];
        for (int i = 0; i < 16; ++i) {
            w[i] = ((uint32_t)msg[offset + i*4] << 24) |
                   ((uint32_t)msg[offset + i*4+1] << 16) |
                   ((uint32_t)msg[offset + i*4+2] << 8) |
                   ((uint32_t)msg[offset + i*4+3]);
        }
        for (int i = 16; i < 64; ++i) {
            w[i] = ssig1(w[i-2]) + w[i-7] + ssig0(w[i-15]) + w[i-16];
        }

        uint32_t a=h[0],b=h[1],c=h[2],d=h[3],e=h[4],f=h[5],g=h[6],hh=h[7];
        for (int i = 0; i < 64; ++i) {
            uint32_t t1 = hh + sig1(e) + ch(e,f,g) + K[i] + w[i];
            uint32_t t2 = sig0(a) + maj(a,b,c);
            hh=g; g=f; f=e; e=d+t1; d=c; c=b; b=a; a=t1+t2;
        }
        h[0]+=a; h[1]+=b; h[2]+=c; h[3]+=d; h[4]+=e; h[5]+=f; h[6]+=g; h[7]+=hh;
    }

    // Output hex string
    const char hex_chars[] = "0123456789abcdef";
    int pos = 0;
    for (int i = 0; i < 8; ++i) {
        for (int j = 28; j >= 0; j -= 4) {
            out_hex[pos++] = hex_chars[(h[i] >> j) & 0xf];
        }
    }
    out_hex[64] = '\0';
}

/**
 * Nhận dạng loại file bằng Magic Bytes (header signature).
 * Trả về tên loại file vào out_type (ví dụ: "PDF", "DOCX", "ZIP", "PNG"...).
 */
NATIVE_EXPORT int fast_detect_magic_bytes(const unsigned char* data, int len, char* out_type, int out_type_size) {
    if (!data || len < 4 || !out_type || out_type_size < 8) {
        if (out_type && out_type_size > 0) { std::snprintf(out_type, out_type_size, "UNKNOWN"); }
        return 0;
    }

    // PDF: %PDF
    if (len >= 5 && data[0]==0x25 && data[1]==0x50 && data[2]==0x44 && data[3]==0x46) {
        std::snprintf(out_type, out_type_size, "PDF");
        return 1;
    }
    // DOCX/XLSX/PPTX/ZIP: PK\x03\x04
    if (data[0]==0x50 && data[1]==0x4B && data[2]==0x03 && data[3]==0x04) {
        // Check for Office Open XML signatures deeper in the file
        if (len > 30) {
            std::string header_str(reinterpret_cast<const char*>(data), std::min(len, 2000));
            if (header_str.find("word/") != std::string::npos || header_str.find("word\\document") != std::string::npos) {
                std::snprintf(out_type, out_type_size, "DOCX"); return 1;
            }
            if (header_str.find("xl/") != std::string::npos) {
                std::snprintf(out_type, out_type_size, "XLSX"); return 1;
            }
            if (header_str.find("ppt/") != std::string::npos) {
                std::snprintf(out_type, out_type_size, "PPTX"); return 1;
            }
        }
        std::snprintf(out_type, out_type_size, "ZIP");
        return 1;
    }
    // DOC/XLS/PPT (OLE2 Compound): \xD0\xCF\x11\xE0
    if (data[0]==0xD0 && data[1]==0xCF && data[2]==0x11 && data[3]==0xE0) {
        std::snprintf(out_type, out_type_size, "DOC_OLE2");
        return 1;
    }
    // PNG: \x89PNG
    if (data[0]==0x89 && data[1]==0x50 && data[2]==0x4E && data[3]==0x47) {
        std::snprintf(out_type, out_type_size, "PNG");
        return 1;
    }
    // JPEG: \xFF\xD8\xFF
    if (len >= 3 && data[0]==0xFF && data[1]==0xD8 && data[2]==0xFF) {
        std::snprintf(out_type, out_type_size, "JPEG");
        return 1;
    }
    // GIF: GIF87a or GIF89a
    if (len >= 6 && data[0]==0x47 && data[1]==0x49 && data[2]==0x46) {
        std::snprintf(out_type, out_type_size, "GIF");
        return 1;
    }
    // EXE/DLL (MZ)
    if (data[0]==0x4D && data[1]==0x5A) {
        std::snprintf(out_type, out_type_size, "EXE_PE");
        return 1;
    }
    // ELF
    if (data[0]==0x7F && data[1]==0x45 && data[2]==0x4C && data[3]==0x46) {
        std::snprintf(out_type, out_type_size, "ELF");
        return 1;
    }
    // RAR: Rar!
    if (len >= 7 && data[0]==0x52 && data[1]==0x61 && data[2]==0x72 && data[3]==0x21) {
        std::snprintf(out_type, out_type_size, "RAR");
        return 1;
    }
    // 7Z: 7z\xBC\xAF
    if (len >= 6 && data[0]==0x37 && data[1]==0x7A && data[2]==0xBC && data[3]==0xAF) {
        std::snprintf(out_type, out_type_size, "7Z");
        return 1;
    }

    std::snprintf(out_type, out_type_size, "UNKNOWN");
    return 0;
}

// ============================================================================
// FAST EXAM CLASSIFIER (N-Gram / Lexical Classifier thuần C++ siêu tốc)
// ============================================================================

namespace exam_classifier {

static std::string fast_utf8_to_lower(const char* text, int len) {
    if (!text || len <= 0) return "";
    int cap = std::min(len, 60000);
    std::string res;
    res.reserve(cap);

    int i = 0;
    while (i < cap) {
        unsigned char b0 = static_cast<unsigned char>(text[i]);
        if (b0 < 0x80) {
            res.push_back(static_cast<char>(std::tolower(b0)));
            i++;
        } else if (b0 == 0xC3 && i + 1 < cap) {
            unsigned char b1 = static_cast<unsigned char>(text[i + 1]);
            if (b1 >= 0x80 && b1 <= 0x9E && b1 != 0x97) {
                res.push_back(static_cast<char>(0xC3));
                res.push_back(static_cast<char>(b1 + 0x20));
            } else {
                res.push_back(text[i]);
                res.push_back(text[i + 1]);
            }
            i += 2;
        } else if (b0 == 0xC4 && i + 1 < cap) {
            unsigned char b1 = static_cast<unsigned char>(text[i + 1]);
            if (b1 == 0x90) {
                res.push_back(static_cast<char>(0xC4));
                res.push_back(static_cast<char>(0x91));
            } else {
                res.push_back(text[i]);
                res.push_back(text[i + 1]);
            }
            i += 2;
        } else if (b0 == 0xE1 && i + 2 < cap) {
            unsigned char b1 = static_cast<unsigned char>(text[i + 1]);
            unsigned char b2 = static_cast<unsigned char>(text[i + 2]);
            if ((b1 == 0xBA || b1 == 0xBB) && ((b2 & 1) == 0)) {
                res.push_back(text[i]);
                res.push_back(text[i + 1]);
                res.push_back(static_cast<char>(b2 + 1));
            } else {
                res.push_back(text[i]);
                res.push_back(text[i + 1]);
                res.push_back(text[i + 2]);
            }
            i += 3;
        } else {
            res.push_back(text[i]);
            i++;
        }
    }
    return res;
}

static bool is_wb(char c) {
    return !std::isalnum(static_cast<unsigned char>(c)) && c != '_';
}

static int count_kw(const std::string& s, const char* sub) {
    if (!sub || sub[0] == '\0') return 0;
    int count = 0;
    size_t sub_len = std::strlen(sub);
    bool check_boundary = (sub_len <= 4);

    size_t pos = s.find(sub, 0);
    while (pos != std::string::npos) {
        bool valid = true;
        if (check_boundary) {
            if (pos > 0 && !is_wb(s[pos - 1])) {
                valid = false;
            }
            if (pos + sub_len < s.size() && !is_wb(s[pos + sub_len])) {
                valid = false;
            }
        }
        if (valid) {
            count++;
            if (count >= 10) break;
        }
        pos = s.find(sub, pos + sub_len);
    }
    return count;
}

struct KwEntry {
    const char* kw;
    double weight;
};

struct SubjDef {
    const char* name;
    std::vector<KwEntry> terms;
};

} // namespace exam_classifier

/**
 * Bộ phân loại đề thi C++ siêu tốc (FastText-style Lexical & Structural Classifier).
 * Thời gian chạy: < 0.5 mili-giây.
 */
NATIVE_EXPORT int fast_classify_exam(
    const char* text,
    int len,
    char* out_subject, int out_subject_size,
    int* out_grade,
    char* out_track, int out_track_size,
    char* out_exam_type, int out_exam_type_size,
    double* out_confidence,
    int* out_question_count,
    int* out_has_answers
) {
    if (!text || len <= 0) {
        if (out_subject && out_subject_size > 0) std::snprintf(out_subject, out_subject_size, "GENERAL");
        if (out_grade) *out_grade = 0;
        if (out_track && out_track_size > 0) std::snprintf(out_track, out_track_size, "thuong");
        if (out_exam_type && out_exam_type_size > 0) std::snprintf(out_exam_type, out_exam_type_size, "ON_TAP");
        if (out_confidence) *out_confidence = 0.0;
        if (out_question_count) *out_question_count = 0;
        if (out_has_answers) *out_has_answers = 0;
        return 0;
    }

    std::string s = exam_classifier::fast_utf8_to_lower(text, len);

    // 1. Phân loại Môn học (Subject)
    using namespace exam_classifier;
    static const SubjDef SUBJS[] = {
        {"MATH", {
            {"môn toán", 15.0}, {"môn: toán", 15.0}, {"toán học", 12.0}, {"toán", 10.0},
            {"toan hoc", 12.0}, {"toanhoc", 10.0}, {"tich phan", 5.0}, {"dao ham", 5.0},
            {"đạo hàm", 5.0}, {"tích phân", 6.0}, {"nguyên hàm", 5.0},
            {"hàm số", 4.0}, {"logarit", 5.0}, {"tiệm cận", 4.0},
            {"bất đẳng thức", 4.0}, {"vectơ", 4.0}, {"tọa độ", 3.0},
            {"oxyz", 5.0}, {"mặt cầu", 4.0}, {"mặt phẳng", 3.0},
            {"phương trình", 2.0}, {"nghiệm", 2.0}, {"sin(", 3.0},
            {"cos(", 3.0}, {"tan(", 2.0}, {"f(x)", 3.0}, {"lim ", 3.0}
        }},
        {"PHYSICS", {
            {"môn vật lí", 15.0}, {"môn vật lý", 15.0}, {"môn: vật lí", 15.0}, {"môn: vật lý", 15.0},
            {"vật lý", 12.0}, {"vật lí", 12.0}, {"vat ly", 15.0}, {"vat lí", 15.0}, {"vatly", 10.0}, {"vatli", 10.0},
            {"dao động điều hòa", 8.0}, {"con lắc lò xo", 7.0}, {"con lắc đơn", 7.0},
            {"dao dong", 7.0}, {"bien do", 5.0},
            {"sóng cơ", 6.0}, {"sóng ánh sáng", 6.0}, {"điện xoay chiều", 7.0},
            {"quang phổ", 5.0}, {"thấu kính", 5.0}, {"động năng", 4.0},
            {"thế năng", 4.0}, {"hạt nhân", 5.0}, {"phóng xạ", 5.0},
            {"bước sóng", 4.0}, {"tần số", 3.0}, {"vôn kế", 4.0},
            {"ampe kế", 4.0}, {"cường độ dòng điện", 4.0}, {"gia tốc", 3.0}
        }},
        {"CHEMISTRY", {
            {"môn hóa học", 15.0}, {"môn: hóa học", 15.0}, {"môn hóa", 12.0},
            {"hóa học", 12.0}, {"hoa hoc", 15.0}, {"hoahoc", 10.0}, {"hoa", 8.0},
            {"este", 8.0}, {"amin", 7.0}, {"ancol", 6.0},
            {"axit cacboxylic", 7.0}, {"cacbohiđrat", 6.0}, {"kim loại kiềm", 6.0},
            {"kết tủa", 5.0}, {"phản ứng", 3.0}, {"đồng phân", 5.0},
            {"h2so4", 5.0}, {"naoh", 5.0}, {"hcl", 5.0},
            {"kim loại fe", 4.0}, {"kim loại cu", 4.0}, {"kim loại al", 4.0},
            {"chất béo", 5.0}, {"polime", 5.0}, {"mol", 4.0}
        }},
        {"BIOLOGY", {
            {"môn sinh học", 15.0}, {"môn: sinh học", 15.0}, {"môn sinh", 12.0},
            {"sinh học", 12.0}, {"sinh hoc", 15.0}, {"sinhhoc", 10.0},
            {"nhiễm sắc thể", 8.0}, {"đột biến gen", 8.0}, {"di truyền học", 7.0},
            {"menden", 6.0}, {"hệ sinh thái", 6.0}, {"quần thể", 6.0},
            {"adn", 6.0}, {"arn", 6.0}, {"tế bào", 4.0}, {"quang hợp", 4.0},
            {"chuỗi thức ăn", 5.0}, {"kiểu gen", 5.0}, {"kiểu hình", 5.0}, {"alen", 5.0}
        }},
        {"INFORMATICS", {
            {"môn tin học", 15.0}, {"môn: tin học", 15.0}, {"môn tin", 12.0},
            {"tin học", 12.0}, {"tin hoc", 15.0}, {"tinhoc", 10.0},
            {"thuật toán", 8.0}, {"quy hoạch động", 8.0}, {"đồ thị", 7.0},
            {"cây nhị phân", 7.0}, {"độ phức tạp", 6.0}, {"subtask", 8.0},
            {"time limit", 7.0}, {"memory limit", 7.0}, {"test case", 6.0},
            {"dữ liệu vào", 5.0}, {"dữ liệu ra", 5.0}, {"stdin", 5.0}, {"stdout", 5.0},
            {"c++", 8.0}, {"cpp", 7.0}, {"#include", 8.0}, {"std::", 7.0}, {"vector<", 7.0}, {"iostream", 7.0},
            {"python", 8.0}, {"def ", 7.0}, {"import ", 6.0}, {"print(", 6.0},
            {"pascal", 8.0}, {"program ", 7.0}, {"begin", 5.0}, {"writeln", 7.0},
            {"java", 8.0}, {"public class", 8.0}, {"system.out", 7.0},
            {"sql", 8.0}, {"cơ sở dữ liệu", 8.0}, {"csdl", 8.0},
            {"dsa", 8.0}, {"cấu trúc dữ liệu", 8.0}, {"segment tree", 8.0}, {"dijkstra", 8.0},
            {"hsg tin", 12.0}, {"tin học trẻ", 12.0}, {"olympic tin", 12.0}, {"vnoi", 8.0}, {"codeforces", 8.0}
        }},
        {"ENGLISH", {
            {"môn tiếng anh", 15.0}, {"môn: tiếng anh", 15.0}, {"english", 10.0},
            {"ielts", 14.0}, {"toeic", 14.0}, {"reading passage", 10.0},
            {"read the following passage", 10.0}, {"mark the letter a, b, c, or d", 10.0},
            {"pronunciation", 8.0}, {"closest in meaning", 8.0}, {"opposite in meaning", 8.0},
            {"word formation", 8.0}, {"cloze test", 8.0}, {"sentence transformation", 8.0},
            {"which of the following", 7.0}, {"grammar", 5.0}, {"vocabulary", 5.0},
            {"passage discusses", 8.0}, {"passage", 5.0}
        }},
        {"LITERATURE", {
            {"môn ngữ văn", 15.0}, {"môn: ngữ văn", 15.0}, {"văn học", 10.0},
            {"ngữ văn", 12.0}, {"ngu van", 15.0}, {"nguvan", 10.0}, {"van hoc", 10.0},
            {"nghị luận xã hội", 8.0}, {"nghị luận văn học", 8.0}, {"đọc hiểu", 6.0},
            {"thông điệp của đoạn trích", 7.0}, {"tác giả", 4.0}, {"tác phẩm", 4.0},
            {"nhà thơ", 5.0}, {"truyện kiều", 6.0}, {"hình tượng", 5.0},
            {"nhân vật", 4.0}, {"cảm nhận của", 5.0}
        }},
        {"HISTORY", {
            {"môn lịch sử", 15.0}, {"môn: lịch sử", 15.0}, {"lịch sử việt nam", 12.0},
            {"lịch sử", 12.0}, {"lich su", 15.0}, {"lichsu", 10.0},
            {"cách mạng tháng tám", 8.0}, {"chiến dịch điện biên phủ", 8.0},
            {"hiệp định giơ-ne-vơ", 8.0}, {"thực dân pháp", 6.0}, {"đế quốc mỹ", 6.0},
            {"đảng cộng sản", 6.0}, {"kháng chiến", 5.0}, {"chiến tranh thế giới", 5.0}
        }},
        {"GEOGRAPHY", {
            {"môn địa lí", 15.0}, {"môn: địa lí", 15.0}, {"môn địa lý", 15.0}, {"môn: địa lý", 15.0},
            {"địa lý", 12.0}, {"địa lí", 12.0}, {"dia ly", 15.0}, {"dia lí", 15.0}, {"dialy", 10.0},
            {"atlat địa lí việt nam", 8.0}, {"gió mùa đông bắc", 7.0},
            {"đồng bằng sông hồng", 7.0}, {"đồng bằng sông cửu long", 7.0},
            {"chuyển dịch cơ cấu", 6.0}, {"khí hậu nhiệt đới", 5.0}, {"địa hình đồi núi", 5.0}
        }},
        {"CIVIC_EDUCATION", {
            {"giáo dục công dân", 15.0}, {"môn: gdcd", 15.0}, {"môn gdcd", 12.0},
            {"giao duc cong dan", 15.0}, {"gdcd", 12.0},
            {"quyền bình đẳng", 8.0}, {"vi phạm pháp luật", 8.0}, {"trách nhiệm pháp lí", 7.0},
            {"công dân có quyền", 6.0}, {"nghĩa vụ của công dân", 6.0}, {"tố tụng", 6.0}
        }}
    };

    std::string best_subject = "GENERAL";
    double max_score = 0.0;

    for (const auto& def : SUBJS) {
        double score = 0.0;
        for (const auto& term : def.terms) {
            int cnt = count_kw(s, term.kw);
            if (cnt > 0) {
                score += term.weight * std::min(cnt, 5);
            }
        }
        if (score > max_score) {
            max_score = score;
            best_subject = def.name;
        }
    }

    // 2. Phân loại Khối lớp (Grade)
    int grade = 0;
    if (s.find("lớp 12") != std::string::npos || s.find("khối 12") != std::string::npos ||
        s.find("toán 12") != std::string::npos || s.find("văn 12") != std::string::npos ||
        s.find("anh 12") != std::string::npos || s.find("lý 12") != std::string::npos ||
        s.find("hóa 12") != std::string::npos || s.find("sinh 12") != std::string::npos ||
        s.find("k12") != std::string::npos) {
        grade = 12;
    } else if (s.find("lớp 11") != std::string::npos || s.find("khối 11") != std::string::npos ||
               s.find("toán 11") != std::string::npos || s.find("văn 11") != std::string::npos ||
               s.find("anh 11") != std::string::npos || s.find("lý 11") != std::string::npos ||
               s.find("hóa 11") != std::string::npos || s.find("sinh 11") != std::string::npos ||
               s.find("k11") != std::string::npos) {
        grade = 11;
    } else if (s.find("lớp 10") != std::string::npos || s.find("khối 10") != std::string::npos ||
               s.find("toán 10") != std::string::npos || s.find("văn 10") != std::string::npos ||
               s.find("anh 10") != std::string::npos || s.find("lý 10") != std::string::npos ||
               s.find("hóa 10") != std::string::npos || s.find("sinh 10") != std::string::npos ||
               s.find("k10") != std::string::npos) {
        grade = 10;
    } else if (s.find("lớp 9") != std::string::npos || s.find("khối 9") != std::string::npos ||
               s.find("vào lớp 10") != std::string::npos || s.find("tuyển sinh 10") != std::string::npos ||
               s.find("k9") != std::string::npos) {
        grade = 9;
    } else if (s.find("lớp 8") != std::string::npos || s.find("khối 8") != std::string::npos || s.find("k8") != std::string::npos) {
        grade = 8;
    } else if (s.find("lớp 7") != std::string::npos || s.find("khối 7") != std::string::npos || s.find("k7") != std::string::npos) {
        grade = 7;
    } else if (s.find("lớp 6") != std::string::npos || s.find("khối 6") != std::string::npos || s.find("k6") != std::string::npos) {
        grade = 6;
    } else {
        // Suy luận theo đặc trưng chương trình nếu không có tiêu đề
        if (s.find("nguyên hàm") != std::string::npos || s.find("tích phân") != std::string::npos ||
            s.find("số phức") != std::string::npos || s.find("este") != std::string::npos ||
            s.find("thpt quốc gia") != std::string::npos || s.find("tốt nghiệp thpt") != std::string::npos) {
            grade = 12;
        } else if (s.find("cấp số cộng") != std::string::npos || s.find("cấp số nhân") != std::string::npos ||
                   s.find("thấu kính") != std::string::npos) {
            grade = 11;
        } else if (s.find("mệnh đề") != std::string::npos || s.find("bảng tuần hoàn") != std::string::npos) {
            grade = 10;
        }
    }

    // 3. Phân loại Thể loại (Track: thuong / hsg / chuyen)
    std::string track = "thuong";
    static const char* CHUYEN_CUES[] = {
        "chuyên", "thpt chuyên", "trường chuyên", "thi chuyên", "vào 10 chuyên",
        "olympic", "olympiad", "hsgqg", "tst", "vnoi", "icpc", "subtask",
        "amsterdam", "chuyên sư phạm", "khtn", "lê hồng phong", "trần đại nghĩa",
        "lam sơn", "phan bội châu", "quốc học"
    };
    for (const char* cue : CHUYEN_CUES) {
        if (s.find(cue) != std::string::npos) {
            track = "chuyen";
            break;
        }
    }
    if (track == "thuong") {
        static const char* HSG_CUES[] = {
            "học sinh giỏi", "hsg", "chọn học sinh giỏi", "kỳ thi hsg",
            "hsg cấp trường", "hsg cấp huyện", "hsg cấp tỉnh", "hsg cấp tp"
        };
        for (const char* cue : HSG_CUES) {
            if (s.find(cue) != std::string::npos) {
                track = "hsg";
                break;
            }
        }
    }

    // 4. Phân loại Dạng đề (Exam Type)
    std::string exam_type = "ON_TAP";
    if (s.find("15 phút") != std::string::npos || s.find("15p") != std::string::npos || s.find("thường xuyên") != std::string::npos) {
        exam_type = "15_PHUT";
    } else if (s.find("1 tiết") != std::string::npos || s.find("45 phút") != std::string::npos || s.find("định kì") != std::string::npos || s.find("định kỳ") != std::string::npos) {
        exam_type = "1_TIET";
    } else if (s.find("giữa kì") != std::string::npos || s.find("giữa kỳ") != std::string::npos || s.find("giữa hk") != std::string::npos) {
        exam_type = "GIUA_KY";
    } else if (s.find("cuối kì") != std::string::npos || s.find("cuối kỳ") != std::string::npos || s.find("học kì 1") != std::string::npos || s.find("học kỳ 1") != std::string::npos || s.find("học kì 2") != std::string::npos || s.find("học kỳ 2") != std::string::npos) {
        exam_type = "CUOI_KY";
    } else if (s.find("thi thử") != std::string::npos || s.find("thpt quốc gia") != std::string::npos || s.find("tốt nghiệp") != std::string::npos) {
        exam_type = "THI_THU_THPT";
    } else if (s.find("tuyển sinh vào 10") != std::string::npos || s.find("tuyển sinh lớp 10") != std::string::npos || s.find("vào lớp 10") != std::string::npos) {
        exam_type = "TUYEN_SINH_10";
    } else if (track == "hsg" || track == "chuyen") {
        exam_type = "HSG";
    }

    // 5. Ước lượng số lượng câu hỏi
    int q_count = 0;
    for (int q = 1; q <= 60; ++q) {
        std::string sq = std::to_string(q);
        std::string p1 = "câu " + sq + ".";
        std::string p2 = "câu " + sq + ":";
        std::string p3 = "câu " + sq + " ";
        std::string p4 = "câu " + sq + "(";
        std::string b1 = "bài " + sq + ".";
        std::string b2 = "bài " + sq + ":";
        std::string b3 = "bài " + sq + " ";
        std::string b4 = "bài " + sq + "(";
        std::string q1 = "question " + sq + ".";
        std::string q2 = "question " + sq + ":";
        std::string q3 = "question " + sq + " ";

        if (s.find(p1) != std::string::npos || s.find(p2) != std::string::npos ||
            s.find(p3) != std::string::npos || s.find(p4) != std::string::npos ||
            s.find(b1) != std::string::npos || s.find(b2) != std::string::npos ||
            s.find(b3) != std::string::npos || s.find(b4) != std::string::npos ||
            s.find(q1) != std::string::npos || s.find(q2) != std::string::npos ||
            s.find(q3) != std::string::npos) {
            q_count = q;
        } else if (q > 3 && q_count == 0) {
            break;
        }
    }

    // 6. Phát hiện có đáp án
    int has_ans = 0;
    if (s.find("đáp án") != std::string::npos || s.find("hướng dẫn chấm") != std::string::npos ||
        s.find("bảng đáp án") != std::string::npos || s.find("lời giải chi tiết") != std::string::npos ||
        s.find("1.a") != std::string::npos || s.find("1.b") != std::string::npos ||
        s.find("1-a") != std::string::npos || s.find("1-b") != std::string::npos ||
        s.find("1. a") != std::string::npos || s.find("1. b") != std::string::npos) {
        has_ans = 1;
    }

    // 7. Độ tin cậy (Confidence)
    double conf = 0.50;
    if (max_score > 30.0) conf = 0.99;
    else if (max_score > 15.0) conf = 0.95;
    else if (max_score > 6.0) conf = 0.88;
    else if (max_score > 0.0) conf = 0.72;

    // Ghi kết quả vào các con trỏ out
    if (out_subject && out_subject_size > 0) std::snprintf(out_subject, out_subject_size, "%s", best_subject.c_str());
    if (out_grade) *out_grade = grade;
    if (out_track && out_track_size > 0) std::snprintf(out_track, out_track_size, "%s", track.c_str());
    if (out_exam_type && out_exam_type_size > 0) std::snprintf(out_exam_type, out_exam_type_size, "%s", exam_type.c_str());
    if (out_confidence) *out_confidence = conf;
    if (out_question_count) *out_question_count = q_count;
    if (out_has_answers) *out_has_answers = has_ans;

    return 1;
}

/**
 * Tính batch cosine similarity giữa 1 vector truy vấn (query_vec, kích thước dim)
 * và N vector tài liệu (doc_vectors, count * dim floats liên tục).
 * Kết quả ghi vào out_scores (mảng count floats).
 * Tối ưu hóa auto-vectorization SIMD với O3.
 */
NATIVE_EXPORT void fast_batch_cosine_similarity(
    const float* query_vec,
    const float* doc_vectors,
    int count,
    int dim,
    float* out_scores
) {
    if (!query_vec || !doc_vectors || !out_scores || count <= 0 || dim <= 0) {
        return;
    }

    // Tính chuẩn L2 của query_vec
    float q_norm_sq = 0.0f;
    for (int d = 0; d < dim; ++d) {
        q_norm_sq += query_vec[d] * query_vec[d];
    }
    float q_norm = std::sqrt(q_norm_sq);
    if (q_norm < 1e-9f) {
        for (int i = 0; i < count; ++i) out_scores[i] = 0.0f;
        return;
    }

    for (int i = 0; i < count; ++i) {
        const float* doc_i = doc_vectors + (static_cast<size_t>(i) * dim);
        float dot = 0.0f;
        float d_norm_sq = 0.0f;

        for (int d = 0; d < dim; ++d) {
            dot += query_vec[d] * doc_i[d];
            d_norm_sq += doc_i[d] * doc_i[d];
        }

        float d_norm = std::sqrt(d_norm_sq);
        if (d_norm > 1e-9f) {
            out_scores[i] = dot / (q_norm * d_norm);
        } else {
            out_scores[i] = 0.0f;
        }
    }
}

} // extern "C"
