# bharatNova setup (~45 min)

## 0. Instagram account (5 min)
1. Account **Professional** kara: Settings -> Account type and tools -> Switch to professional -> **Business** (company sathi) kinva Creator.
2. Profile picture: `assets/profile_picture.png`.
3. Name: `bharatNova | शेती ज्ञान`
4. Bio:
   ```
   रोज शेतीची माहिती, सोप्या मराठीत 🌾
   शेती ज्ञान | सेंद्रिय | bharatNova उत्पादने
   ऑर्डर/माहिती: खालील लिंक 👇
   ```
5. Highlights: `assets/cover_*.png` (4 covers). Pahile 4-5 posts nantar banva.

## 1. Meta app (10 min)
Junach Meta app vapra (navin lagat nahi). developers.facebook.com -> App roles -> Instagram Testers -> `bharatnova` username taka -> Instagram app madhe invite Accept.
Meta app -> Instagram -> API setup with Instagram login -> **Generate access token**. Permissions **tin** pahijet:
`instagram_business_basic`, `instagram_business_content_publish`, **`instagram_business_manage_comments`** (comment sathi: tyashivay comment/reply honar nahi).
**Instagram account ID** (IG_USER_ID) ani **token** (IG_ACCESS_TOKEN) copy kara.

## 2. Products ani photos (aata aadhich bharlele ahet)
- `products.json`: tumchya catalog (PDF + HTML) madhun 21 products bharle. **14 enabled**: Supreemo, Ultra Cane Foliar, Rebooster, Calsibo+, Ultra Cane Soil, Soil Mate, Soil Mate Pro, Germee, Soil Power, Soil Carbo, Areca Nut Boom, Geo Force, Soil Structure, Spreado Plus.
- **7 disabled** (`enabled: false`) kaaran licence/claims aadhi tapasa: Keep On, Super Ninja, Defendo Plus, Mitosafe, N'counter, Fungo Plus, Pro Life. Tapasun `true` kara. Karan `note` field madhe ahe.
- `assets/products/<id>.png`: pratyek product cha photo catalog madhun crop kela ahe. Jast changle photos asle tar fakt tya nava ne replace kara (transparent PNG best).
- `assets/photos/`: tumche real farm/pik photos (subfolders: water, soil, crops, farm, fruits, vegetables). Nasle tar generated hirvya graphics vaparle jatat.
- `assets/logo_lockup.png` ani `assets/profile_picture.png`: catalog madhla BharatNova logo. Tumchyakade original logo file asel tar profile picture ti vapra (jast sharp).

## 3. GitHub (10 min)
1. New **Private** repo `bharatnova-automation`. Ya folder madhle sarv files (`.github` sudha, `fonts/` sudha) upload kara.
2. Settings -> Secrets and variables -> Actions -> **Secrets**: GEMINI_API_KEY, GROQ_API_KEY (optional), IG_USER_ID, IG_ACCESS_TOKEN, CLOUDINARY_CLOUD_NAME, CLOUDINARY_UPLOAD_PRESET (unsigned), GH_PAT (Secrets = Read and write, ya repo sathi).
3. **Variables** (optional): IG_HANDLE=`bharatnova`, BRAND_NAME=`bharatNova`, BRAND_MARK=`bN`, VOICE_FEMALE=`mr-IN-AarohiNeural`, VOICE_MALE=`mr-IN-ManoharNeural`.
   Suruvatila fakt 07:30 Reel chalto. 1-2 athavde nantar `ENABLE_NOON`=`on`, mag `ENABLE_EVENING`=`on`.

## 4. Test
1. Actions -> **bharatNova post** -> Run workflow -> `diagnose` = true.
2. `kind` = reel_agri, `dry_run` = true -> Artifacts -> **bharatnova-output** download: video baghha, voice aika.
3. Chhan watla tar `dry_run` = false. Post + 1 comment automatic.
4. Product ad test: products.json bharlyavar `kind` = reel_ad, dry_run = true.

## Niyam
- Navin account: pahile 1-2 athavde roj 1 Reel. Manually 3-5 posts kara, jast automation spam vatu shakte.
- Jahirat tumchya products chi khari mahitich dyaa. Aushadh/khat cha dose AI sangat nahi, label vaparla jato.
- Commenta auto-reply Marathi madhe, spam/politics skip hotat; kimat/dose cha reply kadhi det nahi.
- Actions free minutes (private ~2000/mahina): roj 3 posts = ~600-900 min; junya repo cha usage Billing madhe baghha.
