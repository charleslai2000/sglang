from sglang.srt.managers.io_struct import (
    SessionParams,
    TokenizedGenerateReqInput,
    msgpack_decode,
    msgpack_encode,
)
from sglang.srt.sampling.sampling_params import SamplingParams


def test_session_params_survive_tokenized_msgpack_ipc_roundtrip():
    req = TokenizedGenerateReqInput(
        rid="session-ipc-roundtrip",
        http_worker_ipc=None,
        input_text=None,
        input_ids=[11, 12],
        input_embeds=None,
        mm_inputs=None,
        token_type_ids=None,
        sampling_params=SamplingParams(),
        return_logprob=False,
        logprob_start_len=0,
        top_logprobs_num=0,
        token_ids_logprob=None,
        stream=False,
        session_id=None,
        session_params=SessionParams(id="stream-session-1"),
    )
    req.wrap_pickle_fields()
    received = msgpack_decode(msgpack_encode(req))
    received.unwrap_pickle_fields()
    assert received.session_id is None
    assert received.session_params == SessionParams(id="stream-session-1")
