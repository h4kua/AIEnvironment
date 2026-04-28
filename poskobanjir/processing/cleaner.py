import pandas as pd


def clean_data(data):
    df = pd.DataFrame(data)

    print("Kolom tersedia:", df.columns)

    # Rename biar konsisten
    df = df.rename(columns={
        "id_pintu_air": "id",
        "nama_pintu_air": "nama",
        "tinggi_air": "tinggi_air",
        "status_siaga": "status",
        "tanggal": "tanggal"
    })

    # Drop duplicate (pakai nama baru)
    if "id" in df.columns and "tanggal" in df.columns:
        df = df.drop_duplicates(subset=["id", "tanggal"])

    if "tinggi_air" in df.columns:
        df["tinggi_air"] = pd.to_numeric(df["tinggi_air"], errors="coerce")

    return df
