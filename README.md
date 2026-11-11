# bharatNova: automated Marathi agri Reels, posts and carousels

Roj: shetkaryansathi Marathi madhe krushi mahiti (Reel + post/carousel) ani bharatNova products chya jahirati.
Female (Aarohi) + male (Manohar) Marathi neural voice, zoom in / zoom out animation, hasiri-sonera theme, Mukta Devanagari font.
Pratyek post khali automatic 1 comment. Stack: Python, Gemini (free) + Groq (backup), edge-tts, Pillow + FFmpeg, Cloudinary, Instagram Graph API, GitHub Actions. Cost: 0.

## Files
- `bharatnova.py`: script writer + voice + video/slides + posting + first comment
- `core.py`: AI calls, Cloudinary, Instagram publish (reel / image / carousel), comments, token refresh
- `products.json`: bharatNova agri products (catalog madhun bharlele; ONLY yatla mahiti jahiratit vaparli jate). Herbovita health products jaanuncha nahit, karan khali pahaa.
- `make_assets.py`: profile picture + highlight covers banvto (already `assets/` madhe ahet)
- `assets/photos/`: tumche farm/pik/product che real photos (jpg/png). Subfolder navache: `water/`, `soil/`, `crops/`, `farm/`, `fruits/`, `vegetables/` (AI scene nusar match hote). Photos nasel tar generated graphics vaparle jatat.
- `assets/products/`: product photos (products.json madhe `image` path)
- `assets/music/`: (optional) royalty-free mp3; halka background music mix hoto
- `.github/workflows/`: `post.yml` (daily posting), `reply-comments.yml` (Marathi replies), `refresh-token.yml` (weekly token)

## Commands (local)
    pip install -r requirements.txt
    python bharatnova.py --sample --kind reel_agri        # look test: no AI, no voice, no posting
    python bharatnova.py --sample --kind carousel
    python bharatnova.py --kind reel_agri --dry-run       # real AI + voice, video banto, post hot nahi
    python bharatnova.py --kind reel_ad --dry-run         # product ad (products.json madhe enabled:true hava)
    python bharatnova.py --kind post --topic "जीवामृत"
    python core.py --reply-comments

## Schedule (IST)
- 07:30 Reel: roj krushi mahiti (hangam nusar: kharif / rabi / unhali)
- 12:30 carousel (even day) kinva single post (odd day): `ENABLE_NOON` = `on`
- 18:30 product: Mon/Wed/Fri ad Reel, Tue/Thu product carousel, Sat/Sun product post: `ENABLE_EVENING` = `on`
- Comments: pratyek post var 1 question comment (retry 3 vela) + divasatun 2 vela Marathi replies.

## Safety rules (prompts madhe aadhich ahet)
- Khoti aakdewari, bajarbhav, sarkari yojanancha aakde, aushadhancha dose: nahi. "Krushi Vidnyan Kendra cha salla ghya" mhantat.
- Jahirat: "double utpanna", "100% guarantee" asle dave nahit; "label vacha, parinam pikanusar badlu shaktat" ase sangte.
