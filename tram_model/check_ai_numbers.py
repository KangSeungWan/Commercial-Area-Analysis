"""B8 (2차 점검): 저장된 AI 해설(outputs/ai_comments.json)의 숫자를 앱이 보내는 정보와 기계로 대조.

같은 조건(기본 시나리오·기본 업종 가중치)으로 상권 정보(ctx)를 다시 만들고, 해설 속 숫자 중 ctx·지표 설명에 없는 숫자를 찾는다.
출력: outputs/ai_number_check.csv (상권, 해설 종류, 대조 안 되는 숫자 수, 목록)
사용: python tram_model/check_ai_numbers.py   ← make_ai_comments.py 로 다시 만든 뒤 꼭 실행
"""
import pandas as pd

import ai_comment as ac


def main():
    d = ac.load_inputs()
    info = d["prof"].set_index("code")
    scen, scen_help, _ = ac.scenarios(d["ts"], d["prof"].columns)
    scen_text = next(iter(scen), "기본")
    weights = ac.default_weights(d["ISW"])
    saved = ac.load_saved() or {"areas": {}}
    rows = []
    for code in info.index:
        e = ac.saved_entry(saved, code)
        if not e:
            continue
        ctx = ac.area_context(code, info, d["fc"], d["IS"], weights, d["ind_area"], d["events"], d["st_areas"], "base",
                              d.get("rentp"), d.get("comp"), d.get("tour"))
        ct = ac.context_text(ctx)
        bad = ac.unverified_numbers(e["text"], ct, ac.build_prompt(ct, scen_text, scen_help))
        rows.append(dict(code=code, name=info.loc[code, "name"], kind=e["kind"], n_unverified=len(bad),
                         unverified=", ".join(f"{v:g}" for v in bad)))
    R = pd.DataFrame(rows)
    R.to_csv(ac.OUT_DIR / "ai_number_check.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 200); pd.set_option("display.max_colwidth", 80)
    print(R.to_string(index=False))
    print(f"\n대조 안 되는 숫자가 있는 해설: {(R.n_unverified > 0).sum()} / {len(R)}")


if __name__ == "__main__":
    main()
