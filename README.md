# Auto-post Threads: Servis Edit Video

Sistem percuma untuk jadualkan post Threads guna **Threads API rasmi Meta** + **GitHub Actions**.
Tak perlu install apa-apa. Semua setup boleh dibuat dari **browser phone** (Chrome/Safari).

## Isi repo

| Fail | Fungsi |
|---|---|
| `content/posts.json` | **Senarai post + jadual.** Ini je fail yang kau edit selalu. |
| `content/posted.json` | Rekod post yang dah keluar (diisi automatik, jangan edit) |
| `content/plan-minggu-1-2.md` | Analisis & strategi kandungan |
| `content/tracker.md` | Catat prestasi setiap post |
| `scripts/threads_post.py` | Skrip yang hantar post |
| `.github/workflows/` | Jadual automatik (GitHub Actions) |

## Cara ia berfungsi

1. GitHub Actions jalan **setiap 30 minit**, dari 7:05 pagi hingga 11:35 malam waktu Malaysia.
2. Skrip semak `posts.json`. Mana-mana post yang **dah sampai masa** dan **belum dipost** akan dihantar ke Threads.
3. Post **tak akan dihantar** kalau:
   - masih ada `[placeholder]` macam `[X]` yang belum diisi
   - `require_media: true` tapi `video_url` masih kosong
   - lebih 500 aksara
   - lewat lebih 6 jam daripada jadual (supaya post lama tak keluar serentak)
4. Masa post mungkin lewat **5 hingga 30 minit** dari jadual, sebab jadual GitHub kadang-kadang tertangguh.

---

## Setup (sekali je, lebih kurang 30 minit)

> 💡 Dalam Chrome phone, tekan ⋮ dan tandakan **"Desktop site"**. Laman Meta Developer dan setting GitHub lebih senang guna dalam mod ni.

### Langkah 1: Buat app di Meta for Developers
1. Buka **developers.facebook.com**, kemudian log masuk dengan Facebook dan daftar sebagai developer (percuma).
2. Tekan **My Apps → Create App**.
3. Pilih use case **"Access the Threads API"**, kemudian beri nama app (contoh: `naz3l-autopost`).
4. Pergi ke **Use cases → Threads API → Customize**. Pastikan permission ni ada:
   - `threads_basic`
   - `threads_content_publish`

### Langkah 2: Jadikan akaun Threads kau sebagai tester
1. Dalam app tadi, pergi ke **App roles → Roles → Add people**. Pilih **Threads Tester** dan masukkan username `naz3l_`.
2. Buka **threads.com** (browser), kemudian **Settings → Account → Website permissions → Invites**, dan **Accept** jemputan tu.

### Langkah 3: Dapatkan access token
1. Balik ke **Use cases → Threads API → Customize → Settings**.
2. Cari **User Token Generator**, kemudian tekan **Generate access token** untuk akaun `naz3l_`.
3. **Copy** token tu.
   - ⚠️ **Jangan share token dengan sesiapa**, termasuk dalam chat. Token tu macam password akaun Threads kau.

### Langkah 4: Simpan token dalam GitHub Secrets
1. Buka repo ni di **github.com** (mod Desktop site). App GitHub tak boleh edit secrets.
2. Pergi ke **Settings → Secrets and variables → Actions → New repository secret**.
3. Isi seperti ini:
   - **Name:** `THREADS_ACCESS_TOKEN`
   - **Secret:** paste token tadi

### Langkah 5 (digalakkan): Auto-refresh token
Token Threads biasanya tamat dalam **60 hari**. Untuk refresh automatik:
1. Buka **github.com/settings/personal-access-tokens**, kemudian **Generate new token** (jenis fine-grained).
2. Bahagian **Repository access**, pilih *Only select repositories* dan pilih repo `threads` sahaja.
3. Bahagian **Permissions**, set **Secrets** kepada **Read and write**.
4. Copy token tu, dan simpan sebagai secret baru dengan nama **`GH_PAT`** (cara sama macam Langkah 4).

Kalau kau skip langkah ni, kau kena ulang Langkah 3 dan 4 setiap kira-kira 50 hari.

### Langkah 6: Test
1. Pergi ke tab **Actions → Auto-post Threads → Run workflow**, pilih mod **test_token**, dan tekan Run. Ini cuma semak token, tak post apa-apa.
2. Untuk test betul-betul, tambah satu post dalam `posts.json` dengan masa 5 minit dari sekarang, kemudian **Run workflow** tanpa Dry run.

---

## Edit atau tambah post (dari phone)

1. Buka `content/posts.json` di github.com, dan tekan ikon ✏️.
2. Setiap post bentuknya macam ni:

```json
{
  "id": "p15",
  "scheduled_at": "2026-11-23T21:00:00+08:00",
  "topic_tag": "edit video",
  "text": "Teks post kau...",
  "video_url": "",
  "image_url": "",
  "require_media": false
}
```

- `id` mesti **unik** (p15, p16, ...)
- `scheduled_at` ikut format `TAHUN-BULAN-HARIjam:minit:00+08:00` (+08:00 = waktu Malaysia)
- Untuk baris baru dalam teks, tulis `\n`. Untuk tanda petik, tulis `\"`.
- Pastikan ada koma `,` antara setiap `{ ... }`.

3. Tekan **Commit changes**. Workflow **"Semak posts.json"** akan jalan sendiri. Kalau ia ❌, maksudnya ada kesilapan format.

### Post dengan video/gambar (guna Google Drive)
Threads API tak terima fail dari phone. Server Meta akan **download sendiri** video dari satu link awam.

1. Upload video ke Google Drive. Format: **MP4/MOV**, maksimum **5 minit**, maksimum **1GB**.
2. Pada **fail video** (bukan folder), tekan ⋮ → **Share** → **General access: Anyone with the link** → **Copy link**.
3. Paste link tu dalam `video_url` post berkenaan. Contoh:
   `"video_url": "https://drive.google.com/file/d/1AbCdEf.../view?usp=sharing"`
4. Skrip akan tukar link Drive tu jadi link download terus secara automatik.
5. Commit. Workflow **"Semak posts.json"** akan uji link tu dan tunjuk `link OK ✓` atau masalahnya.

⚠️ **Link folder tak boleh guna.** Mesti link setiap fail video.
⚠️ Kalau Google sekat download (contohnya video terlalu banyak kali didownload), post tu akan gagal dan direkod dalam log Actions. Kalau jadi, post sendiri dari app Threads.

---

## Insights (data prestasi)

> ⏸️ **Belum diaktifkan.** Jadual harian dimatikan sehingga token ada permission insights. Selepas setup di bawah, buang tanda `#` pada baris `schedule` dan `cron` dalam `.github/workflows/threads-insights.yml`.

Bila aktif, workflow **"Kumpul insights Threads"** jalan setiap hari pukul **11:47 malam** dan simpan:

| Fail | Isi |
|---|---|
| `content/insights/RINGKASAN.md` | Jadual mudah baca: followers + views/likes/replies/reposts/shares setiap post |
| `content/insights/latest.json` | Data penuh terkini |
| `content/insights/history.csv` | Rekod harian (untuk tengok trend) |

Token perlu ada permission **`threads_manage_insights`**:
1. Meta Developer → **Use cases → Customize → Permissions and features** → tekan **+ Add** pada `threads_manage_insights`.
2. **Settings → User Token Generator → Generate Access Token** (jana token baru).
3. GitHub → **Settings → Secrets and variables → Actions** → ✏️ pada `THREADS_ACCESS_TOKEN` → paste token baru → **Update secret**.
4. **Actions → Kumpul insights Threads → Run workflow** untuk test.

⚠️ Repo ni public, jadi data insights pun boleh dilihat orang lain. Tukar repo jadi private kalau tak nak.
