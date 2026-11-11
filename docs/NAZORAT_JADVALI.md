# Nazorat jadvali dasturiga ulash

**Nazorat jadvali** imtihonlarni auditoriyalarga taqsimlaganda, shu sahifa orqali universitetingiz
auditoriyalarida **qachon dars va qachon imtihon borligini** biladi — boshqa fakultetlar HEMIS'ga
allaqachon kiritgan imtihonlar ham hisobga olinadi va ular band xonaga imtihon qo'yilmaydi.

Buning uchun `hisobot` ilovasini o'z serveringizdagi Django saytga bir marta o'rnatasiz,
so'ng uning manzilini dasturga kiritasiz.

---

## 1. Kerakli narsalar

- Django sayt ishlayotgan server (Django 4.2 yoki yangisi, Python 3.10+)
- Universitetingiz HEMIS REST API manzili, masalan `https://student.<universitet>.uz/rest/v1/data/`
- HEMIS API tokeni — HEMIS administratoringizdan oling. **Tokenni hech kimga bermang va GitHub'ga yuklamang.**

## 2. Serverga o'rnatish

1. Ilovani yuklab oling: <https://github.com/copilotgit/django-hisobot/archive/refs/heads/main.zip>
   (yoki `git clone https://github.com/copilotgit/django-hisobot.git`).
2. Arxivdagi **`hisobot`** papkasini saytingizning `manage.py` fayli turgan papkaga ko'chiring.
3. Kutubxonalarni o'rnating:

   ```bash
   pip install requests python-dotenv
   ```

4. **settings.py** — `INSTALLED_APPS` ro'yxatiga qo'shing:

   ```python
   INSTALLED_APPS = [
       # ...
       "hisobot",
   ]
   ```

5. **urls.py** — manzil qo'shing:

   ```python
   from django.urls import include, path

   urlpatterns = [
       # ...
       path("hisobot/", include("hisobot.urls")),
   ]
   ```

6. **.env** — `manage.py` yonida `.env` fayl yarating (namuna: `.env.example`):

   ```ini
   HEMIS_API_URL=https://student.<universitet>.uz/rest/v1/data/
   HEMIS_API_TOKEN=<tokeningiz>
   ```

7. Ma'lumotlarni birinchi marta yuklang (bir necha daqiqa davom etadi):

   ```bash
   python manage.py hisobot_refresh
   ```

8. Saytni qayta ishga tushiring (masalan `sudo systemctl restart gunicorn`) va brauzerda oching:
   `https://<saytingiz>/hisobot/` — auditoriyalar jadvali ko'rinishi kerak.

### Ma'lumotlarni yangilab turish

Har kuni ertalab avtomatik yangilansin (cron):

```bash
crontab -e
# har kuni 06:00 da
0 6 * * * cd /srv/sayt && /srv/sayt/.venv/bin/python manage.py hisobot_refresh
```

yoki `.env` ga `HISOBOT_AUTO_REFRESH_HOURS=12` yozing — sahifa ochilganda ma'lumot 12 soatdan
eski bo'lsa, o'zi yangilanadi. Xodimlar (`is_staff`) sahifadagi **HEMIS'dan yangilash** tugmasini ham bosishi mumkin.

### Sahifani yopiq qilish (ixtiyoriy)

Hisobotda o'qituvchi va guruh nomlari bor. Sahifani faqat kirgan foydalanuvchilarga ko'rsatish uchun:

```ini
HISOBOT_LOGIN_REQUIRED=true
HISOBOT_API_KEY=<uzun tasodifiy matn>
```

`HISOBOT_API_KEY` — Nazorat jadvali dasturi sahifaga login qilmasdan ulanishi uchun kalit.

## 3. Nazorat jadvali dasturiga ulash

1. Brauzerda tekshiring: `https://<saytingiz>/hisobot/data.json` JSON qaytarishi kerak
   (yopiq sahifada — kalit bilan: `.../data.json?key=<kalit>`).
2. Nazorat jadvali → **Auditoriyalar** bo'limi → **🏫 Universitet sahifasi** tugmasi.
3. **Manzil** maydoniga saytingizdagi sahifa manzilini yozing: `https://<saytingiz>/hisobot/`
   (yopiq sahifa bo'lsa, **Kalit** maydoniga `HISOBOT_API_KEY` ni).
4. **Tekshirish va saqlash** ni bosing — "Ulandi: N ta auditoriya, M ta imtihon" chiqadi.
5. Endi Auditoriyalar bo'limida **"Imtihoni bor auditoriyalarga imtihon qo'ymaslik"** belgisi faol bo'ladi
   (ulanmaguncha u kulrang turadi). Belgilangan bo'lsa, dastur boshqa imtihonlar o'tkaziladigan xonalarni
   o'sha sana va juftda boshqa guruhlarga bermaydi. Sahifadagi darslar ham dars bandligiga qo'shiladi.

Dastur ma'lumotni har safar ochilganda va **Dars bandligini yangilash** tugmasi bosilganda qayta oladi.

## Muammolar

| Belgi | Sabab |
|---|---|
| `data.json` 404 | Ma'lumot hali yuklanmagan — `python manage.py hisobot_refresh` |
| `data.json` 403 | Sahifa yopiq — dasturga `HISOBOT_API_KEY` ni kiriting |
| `refresh` xatosi "token qabul qilinmadi" | `HEMIS_API_TOKEN` noto'g'ri yoki muddati o'tgan |
| Sahifada hech narsa yo'q | Boshqa binoni tanlang yoki haftani almashtiring |
