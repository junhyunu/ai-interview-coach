"""OpenAI 호출은 이 파일 한 곳에서만 한다."""

import json
import os

from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)

load_dotenv()

DEFAULT_MODEL = "gpt-6-luna"


class LLMError(Exception):
    """화면에 그대로 보여 줄 한국어 한 줄 에러."""


def model_name(for_eval: bool = False) -> str:
    base = os.getenv("OPENAI_MODEL") or DEFAULT_MODEL
    if for_eval:
        return os.getenv("OPENAI_EVAL_MODEL") or base
    return base


def _client() -> OpenAI:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise LLMError("API 키가 없어요. .env 파일에 OPENAI_API_KEY 를 넣어 주세요.")
    return OpenAI(api_key=key, timeout=90)


def ask_json(instructions: str, user_input: str, schema: dict, name: str, for_eval: bool = False) -> dict:
    """instructions + user_input 을 보내고, strict JSON 스키마에 맞는 dict 를 돌려준다."""
    try:
        resp = _client().responses.create(
            model=model_name(for_eval),
            instructions=instructions,
            input=user_input,
            text={"format": {"type": "json_schema", "name": name, "schema": schema, "strict": True}},
        )
    except AuthenticationError:
        raise LLMError("API 키가 틀렸어요. .env 의 OPENAI_API_KEY 를 확인해 주세요.") from None
    except RateLimitError as e:
        if "insufficient_quota" in str(getattr(e, "code", "")) or "quota" in str(e).lower():
            raise LLMError("OpenAI 크레딧이 부족해요. 결제 · 사용 한도를 확인해 주세요.") from None
        raise LLMError("요청이 너무 많아요. 잠시 뒤 다시 시도해 주세요.") from None
    except (APIConnectionError, APITimeoutError):
        raise LLMError("OpenAI 에 연결하지 못했어요. 인터넷 연결을 확인해 주세요.") from None
    except NotFoundError:
        raise LLMError("모델을 찾을 수 없어요. .env 의 OPENAI_MODEL 이름을 확인해 주세요.") from None
    except PermissionDeniedError:
        raise LLMError("이 키로는 해당 모델을 쓸 수 없어요. 모델 권한을 확인해 주세요.") from None
    except BadRequestError:
        raise LLMError("요청 형식이 맞지 않아요. 입력이 너무 길지 않은지 확인해 주세요.") from None

    if getattr(resp, "status", None) == "incomplete":
        raise LLMError("AI 답이 중간에 끊겼어요. 다시 시도해 주세요.")
    try:
        return json.loads(resp.output_text)
    except (json.JSONDecodeError, TypeError):
        raise LLMError("AI 답을 읽지 못했어요. 다시 시도해 주세요.") from None
