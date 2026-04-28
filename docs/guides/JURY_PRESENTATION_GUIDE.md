# Jury Presentation Guide

## Problem

Banjir di Jakarta bukan hanya masalah air. Ini adalah masalah keselamatan, mobilitas, kesehatan publik, dan ketimpangan sosial.

Dalam banyak kasus, keputusan penting harus dibuat sebelum genangan besar benar-benar terlihat. Tantangannya adalah:

- data lapangan terpisah-pisah
- cuaca berubah cepat
- sistem prediksi sering kuat di laboratorium, tetapi lemah saat dipakai realtime

## Approach

Kami membangun sistem Flood Prediction yang tidak hanya memprediksi, tetapi juga menghubungkan tiga jenis sinyal penting:

- cuaca realtime dari OpenWeather
- peringatan resmi BMKG
- kondisi hidrologi lapangan dari Posko Banjir

Sistem ini menggunakan dua model:

1. Model historis
   Dipakai untuk menunjukkan kekuatan prediksi berbasis data historis yang kaya.

2. Model realtime-native
   Dipakai untuk kondisi operasional nyata, karena dilatih dengan feature yang memang tersedia saat inference realtime.

## Why Two Models?

Ini bukan duplikasi. Ini adalah desain yang disengaja.

- Model historis memberi kedalaman analisis dan baseline performa.
- Model realtime-native memberi konsistensi antara training dan deployment.

Dengan kata lain:

- satu model kuat untuk pembelajaran historis
- satu model kuat untuk keputusan operasional

## Innovation

Inovasi utama sistem ini bukan hanya akurasi model, tetapi kualitas integrasinya.

### 1. Realtime-Native Design

Banyak sistem AI menggunakan feature saat training yang tidak benar-benar tersedia saat realtime. Kami menghindari masalah itu dengan membangun model kedua yang hanya memakai sinyal operasional:

- rainfall
- humidity
- temperature
- BMKG alert severity/certainty/urgency
- water level ratio dari Posko Banjir

### 2. Temporal Awareness

Kami tidak hanya melihat cuaca “saat ini”, tetapi juga pola perubahan:

- lag rainfall
- rolling rainfall
- water level delta

Ini penting, karena banjir sering terjadi bukan hanya akibat satu puncak hujan, tetapi akumulasi dan keterlambatan respons sistem drainase.

### 3. Responsible AI Layer

Sistem tidak berhenti pada angka probabilitas. Kami menambahkan:

- `data_quality`
- `confidence_score`
- OOD detection
- SHAP-based explanation
- `risk_interpretation`
- `recommended_action`

Jadi sistem ini lebih transparan dan lebih aman dipakai dalam konteks keputusan publik.

## Scientific Validity

### Tentang `bootstrap_proxy`

Kami tidak menyembunyikan fakta bahwa histori operasional realtime penuh belum tersedia untuk semua sinyal.

Karena itu kami memakai pendekatan `bootstrap_proxy`.

Cara menjelaskannya ke juri:

> Ini bukan kelemahan desain, melainkan strategi transisi yang bertanggung jawab. Sistem kami sudah operasional sekarang, tetapi juga dirancang untuk terus membaik seiring terkumpulnya histori realtime asli.

Artinya:

- sistem bisa dipakai hari ini
- sistem akan menjadi lebih kuat besok
- arsitekturnya sudah siap menerima data observasional penuh tanpa perlu dibangun ulang

Ini yang kami sebut sebagai **progressive system**:

- mulai dari model historis
- beralih ke model realtime-native
- lalu berkembang ke retraining periodik berbasis histori lapangan nyata

## Social and Environmental Impact

### Social Impact

- membantu keputusan siaga lebih cepat
- mendukung komunikasi risiko yang lebih jelas
- mengurangi keterlambatan respon di wilayah padat penduduk
- berpotensi melindungi kelompok paling rentan yang biasanya terdampak paling awal

### Environmental Impact

- mendukung manajemen air yang lebih adaptif
- membantu identifikasi pola risiko berbasis cuaca dan hidrologi
- memperkuat kesiapan kota terhadap intensifikasi cuaca ekstrem akibat perubahan iklim

## Key Selling Points

- Dual-model architecture: kuat secara historis dan valid secara operasional
- Realtime pipeline terintegrasi: BMKG + OpenWeather + Posko Banjir
- Explainable AI: tidak hanya memberi skor, tetapi juga alasan
- Responsible AI: ada data quality, confidence score, dan OOD detection
- Actionable output: sistem memberi interpretasi risiko dan rekomendasi tindakan
- Progressive system: siap berkembang saat histori realtime makin kaya

## Simple Component Explanation

### `poskobanjir/`

Mengambil dan menyatukan data realtime dari sumber eksternal.

### `app/services/`

Menjalankan model historis, adapter, quality control, dan pelaporan.

### `app/realtime_native/`

Menjalankan model operasional yang hanya memakai feature yang benar-benar tersedia realtime.

### `app/api/`

Menyediakan endpoint untuk demo dan integrasi deployment.

## Suggested 2-Minute Pitch

Jakarta menghadapi banjir bukan hanya sebagai masalah cuaca, tetapi sebagai masalah keselamatan dan ketahanan kota. Tantangan utamanya adalah bagaimana mengubah data yang tersebar menjadi keputusan yang cepat, jelas, dan dapat dipercaya.

Karena itu kami membangun Flood Prediction System yang menggabungkan tiga sumber sinyal penting: cuaca realtime, peringatan resmi BMKG, dan kondisi tinggi muka air dari Posko Banjir.

Keunggulan utama kami adalah desain dual-model. Model pertama memberi baseline historis yang kuat. Model kedua adalah realtime-native model yang hanya memakai feature yang benar-benar tersedia saat sistem berjalan. Ini penting, karena banyak solusi AI gagal di tahap deployment akibat mismatch antara feature training dan feature inference.

Kami juga menambahkan lapisan Responsible AI: data quality, confidence score, out-of-distribution detection, dan explainability. Jadi sistem ini tidak hanya memberi skor risiko, tetapi juga menjelaskan seberapa yakin sistem, kenapa prediksi itu muncul, dan tindakan apa yang sebaiknya dilakukan.

Dengan pendekatan ini, solusi kami tidak hanya akurat, tetapi juga operasional, transparan, dan siap dikembangkan menjadi sistem ketahanan banjir yang terus belajar dari data lapangan nyata.

## Potential Jury Questions

### Mengapa memakai dua model, bukan satu saja?

Karena kami memisahkan tujuan ilmiah dan tujuan operasional. Model historis memberi kedalaman, sedangkan model realtime-native memberi validitas deployment.

### Apakah `bootstrap_proxy` berarti data Anda lemah?

Tidak. Itu berarti kami transparan tentang tahap perkembangan sistem. Kami tidak memaksakan klaim palsu. Sistem ini sudah siap dipakai sekarang dan dirancang untuk meningkat seiring histori realtime terkumpul.

### Apa yang membuat sistem ini berbeda dari dashboard cuaca biasa?

Kami tidak hanya menampilkan cuaca. Kami menggabungkan cuaca, alert resmi, dan kondisi hidrologi, lalu mengubahnya menjadi prediksi risiko yang bisa ditindaklanjuti.

### Bagaimana sistem ini membantu masyarakat?

Dengan mempercepat peringatan dini, memperjelas komunikasi risiko, dan membantu pengambilan keputusan sebelum dampak banjir membesar.

### Apa langkah pengembangan berikutnya?

- retraining berkala berbasis histori realtime asli
- integrasi spasial tingkat kelurahan
- forecasting 3 sampai 12 jam ke depan
- dashboard publik dan dashboard operator yang berbeda per kebutuhan
