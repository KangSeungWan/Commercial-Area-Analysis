"""landprice_long.pkl 을 pyarrow 없는 환경에서도 읽을 수 있게, 1990~2020 공시지가(D151 CSV)만으로 같은 필지×연도 표를 다시 만든다.
build_landprice.load_prices() 와 같은 규칙(1월 1일 정기공시, 19자리 PNU, 최신 공시 파일 우선). 2021~2026 은 dbf 가 필요해 포함하지 않음.
출력: outputs/landprice_long_1990_2020.csv.gz (pnu, year, price)
"""
import zipfile
import pandas as pd
import config as C

LP = C.RAW_DIR / "공시지가"
FILES = ["AL_30_D151_20200925_csv.zip", "AL_30_D151_20160919.csv", "AL_D151_30_20151231.csv"]   # 최신 우선


def _read(src):
    use = lambda c: c in ("고유번호", "기준년도", "기준연도", "기준월", "공시지가", "개별공시지가")
    for enc in ("cp949", "utf-8-sig"):
        try:
            d = pd.read_csv(src() if callable(src) else src, encoding=enc, dtype=str, usecols=use)
            return d.rename(columns={"기준년도": "year", "기준연도": "year", "공시지가": "price", "개별공시지가": "price",
                                     "고유번호": "pnu", "기준월": "month"})
        except UnicodeDecodeError:
            continue


def main():
    parts = []
    for name in FILES:
        f = LP / name
        if f.suffix == ".zip":
            z = zipfile.ZipFile(f)
            for n in [n for n in z.namelist() if n.lower().endswith(".csv")]:
                parts.append(_read(lambda n=n: z.open(n)))
        else:
            parts.append(_read(f))
        print(name, len(parts[-1]), flush=True)
    L = pd.concat(parts, ignore_index=True)
    L = L[L.month.fillna("01").str.zfill(2) == "01"]
    L = L[L.pnu.astype(str).str.match(r"^\d{19}$")]
    L["pnu"] = L.pnu.astype("int64")
    L["year"] = pd.to_numeric(L.year, errors="coerce")
    L["price"] = pd.to_numeric(L.price, errors="coerce")
    L = L.dropna(subset=["year", "price"])
    L = L[L.price > 0].drop_duplicates(["pnu", "year"])
    G = pd.read_csv(C.OUT_DIR / "landprice_parcels.csv.gz", usecols=["pnu"])
    L = L[L.pnu.isin(G.pnu)].astype({"pnu": "int64", "year": "int16", "price": "int64"})[["pnu", "year", "price"]]
    L.to_csv(C.OUT_DIR / "landprice_long_1990_2020.csv.gz", index=False)
    print(len(L), L.year.min(), L.year.max())


if __name__ == "__main__":
    main()
