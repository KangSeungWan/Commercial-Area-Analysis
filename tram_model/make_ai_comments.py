"""20개 상권 AI 해설을 미리 만들어 outputs/ai_comments.json 에 저장.

발표장 네트워크가 끊기거나 API 호출이 실패해도, 앱이 이 저장본을 대신 보여 줌.
분석 결과(run_all.py)를 다시 돌렸다면 이 스크립트도 다시 실행해 해설을 최신 수치에 맞추세요.

사용 (프로젝트 폴더에서):
  python tram_model/make_ai_comments.py              # 20개 상권 전부 새로 만들기
  python tram_model/make_ai_comments.py --missing    # 저장본에 없는 상권만
  python tram_model/make_ai_comments.py --only A03,A12
  python tram_model/make_ai_comments.py --dry-run    # API 호출 없이 보낼 내용만 점검

API 키: 환경변수 GEMINI_API_KEY → 없으면 .streamlit/secrets.toml 의 GEMINI_API_KEY (화면에 출력하지 않음)
기준: 업종 점수 기본 가중치 · 트램 효과 '기본' 시나리오 (앱 첫 화면과 같은 조건)
"""
import argparse
import json
import os
import sys
import time
import tomllib
from datetime import datetime
from pathlib import Path

import ai_comment as ac

ROOT = ac.HERE.parent
SECRETS = ROOT / ".streamlit" / "secrets.toml"


def api_key():
    k = os.environ.get("GEMINI_API_KEY")
    if k:
        return k
    try:
        with open(SECRETS, "rb") as f:
            return tomllib.load(f).get("GEMINI_API_KEY")
    except (OSError, tomllib.TOMLDecodeError):
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="쉼표로 구분한 상권 코드 (예: A03,A12)")
    ap.add_argument("--missing", action="store_true", help="저장본에 없는 상권만 만들기")
    ap.add_argument("--model", default=os.environ.get("GEMINI_MODEL", ac.DEFAULT_MODEL))
    ap.add_argument("--delay", type=float, default=2.0, help="호출 사이 쉬는 시간(초, 요청 한도 대비)")
    ap.add_argument("--dry-run", action="store_true", help="API를 부르지 않고 상권 정보·질문 글만 점검")
    a = ap.parse_args()

    d = ac.load_inputs()
    if d["prof"] is None:
        sys.exit("outputs/area_profile.csv 가 없습니다. 먼저 python tram_model/run_all.py 를 실행하세요.")
    info = d["prof"].set_index("code")
    scen, scen_help, TS = ac.scenarios(d["ts"], d["prof"].columns)
    scen_text = next(iter(scen), "기본")                          # 첫 항목 = 기본 시나리오
    weights = ac.default_weights(d["ISW"])

    saved = ac.load_saved() or {"areas": {}}
    codes = list(info.index)
    if a.only:
        want = [c.strip().upper() for c in a.only.split(",") if c.strip()]
        bad = [c for c in want if c not in info.index]
        if bad:
            sys.exit(f"없는 상권 코드: {', '.join(bad)}")
        codes = want
    if a.missing:
        codes = [c for c in codes if not ac.saved_entry(saved, c)]
    if not codes:
        print("새로 만들 상권이 없습니다.")
        return

    key = None if a.dry_run else api_key()
    if not a.dry_run and not key:
        sys.exit("API 키를 찾지 못했습니다. 환경변수 GEMINI_API_KEY 나 .streamlit/secrets.toml 을 확인하세요.")

    print(f"{len(codes)}개 상권 · 모델 {a.model} · 시나리오 {scen_text}" + (" · 점검만(dry-run)" if a.dry_run else ""))
    ok, fail = 0, []
    for i, code in enumerate(codes, 1):
        ctx = ac.area_context(code, info, d["fc"], d["IS"], weights, d["ind_area"], d["events"], d["st_areas"], "base")
        prompt = ac.build_prompt(ac.context_text(ctx), scen_text, scen_help)
        label = f"[{i:>2}/{len(codes)}] {code} {info.loc[code, 'name']}"
        if a.dry_run:
            print(f"{label}: 정보 {len(ctx)}항목, 질문 {len(prompt):,}자")
            continue
        try:
            text = ac.generate(prompt, key, a.model)
        except Exception as e:                                      # 실패한 상권은 이전 저장본을 그대로 둠
            fail.append(code)
            print(f"{label}: 실패 ({type(e).__name__}: {str(e)[:160]})")
        else:
            ok += 1
            saved["areas"][code] = {"name": info.loc[code, "name"], "text": text.strip(),
                                    "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                    "scenario": scen_text, "model": a.model}
            print(f"{label}: 완료 ({len(text):,}자)")
        if i < len(codes):
            time.sleep(a.delay)

    if a.dry_run:
        return
    if ok:
        saved.update(generated_at=datetime.now().strftime("%Y-%m-%d"), model=a.model, scenario=scen_text,
                     note="make_ai_comments.py 로 미리 만든 AI 상권 해설. 앱에서 실시간 호출이 실패하면 이 해설을 보여 줌.")
        saved["areas"] = dict(sorted(saved["areas"].items()))
        tmp = ac.SAVED_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(ac.SAVED_PATH)                                  # 쓰는 도중 멈춰도 기존 저장본이 깨지지 않게
    total = sum(1 for c in info.index if ac.saved_entry(saved, c))
    print(f"\n완료 {ok}개, 실패 {len(fail)}개 → {ac.SAVED_PATH.relative_to(ROOT)} (저장된 상권 {total}/{len(info)})")
    if fail:
        print(f"실패한 상권만 다시: python tram_model/make_ai_comments.py --only {','.join(fail)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
