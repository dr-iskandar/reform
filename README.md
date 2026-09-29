# ReForm OCR Extractor

Sample web app untuk membaca data terstruktur dari softcopy dokumen/foto menggunakan OCR di browser, lalu mengekspor hasil ke Excel.

## Fitur
- Upload JPG/PNG/PDF.
- Preview halaman pertama PDF.
- Pilih area tertentu (ROI) dengan drag mouse agar OCR fokus ke area yang dibutuhkan.
- OCR berjalan lokal di browser menggunakan Tesseract.js.
- Parsing otomatis field umum: Kota, Kecamatan, Kelurahan, Latitude, Longitude, Tanggal/Waktu.
- Hasil bisa diedit manual sebelum ditambahkan ke tabel.
- Export ke Excel (.xlsx) dan CSV.
- Tidak ada backend; cocok untuk demo cepat.

## Menjalankan
Buka `index.html` langsung di browser modern, atau jalankan static server:

```bash
python3 -m http.server 8000
```

Lalu buka http://localhost:8000.

## Catatan
Untuk produksi, OCR sebaiknya diganti/ditambah dengan engine server-side atau OCR cloud jika dokumen sangat bervariasi, resolusi rendah, atau butuh akurasi tinggi.
