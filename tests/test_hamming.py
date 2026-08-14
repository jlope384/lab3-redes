from src.linklayer.framing import bits_to_text, decode_frame, encode_frame, text_to_bits
from src.linklayer.hamming import decode as hamming_decode
from src.linklayer.hamming import encode as hamming_encode


def test_hamming_block_roundtrip_no_error():
    for data in ["0000", "1111", "1010", "0110", "1001"]:
        codeword = hamming_encode(data)
        assert len(codeword) == 7
        recovered, had_error, _ = hamming_decode(codeword)
        assert recovered == data
        assert had_error is False


def test_hamming_block_corrects_single_bit_error():
    data = "1011"
    codeword = hamming_encode(data)
    for flip_pos in range(len(codeword)):
        corrupted = list(codeword)
        corrupted[flip_pos] = "1" if corrupted[flip_pos] == "0" else "0"
        recovered, had_error, error_pos = hamming_decode("".join(corrupted))
        assert recovered == data
        assert had_error is True
        assert error_pos == flip_pos + 1


def test_frame_roundtrip_arbitrary_text():
    for text in ["", "a", "hola mundo", "Hamming(7,4) ñ€", "x" * 50]:
        bits = text_to_bits(text)
        frame = encode_frame(bits)
        recovered_bits = decode_frame(frame)
        assert bits_to_text(recovered_bits) == text
