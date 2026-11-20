"""Data contoh (SEED_DEMO=true). Koordinat perkiraan; hanya untuk uji, bukan data resmi."""
from . import events

DEMO = [
    ("Kampung Adat Cireundeu", "budaya-sejarah", -6.9497, 107.5375,
     "Kampung adat di Cimahi Selatan yang warganya dikenal mengolah singkong sebagai makanan pokok pengganti beras. "
     "Pengunjung dapat melihat pengolahan rasi dan mengenal kehidupan adat setempat.", "Kampung Cireundeu"),
    ("Gua Pawon", "alam", -6.8333, 107.4333,
     "Gua karst di kawasan Padalarang, Bandung Barat, yang dikenal sebagai situs arkeologi prasejarah. "
     "Cocok untuk wisata edukasi sejarah dan fotografi alam.", "Gua Pawon"),
    ("Curug Cimahi", "alam", -6.8110, 107.5560,
     "Air terjun di Cisarua, Bandung Barat, dengan area pandang dan jalur jalan kaki yang pendek. "
     "Ramai pada akhir pekan, jadi paling nyaman dikunjungi pada hari kerja.", "Curug Cimahi"),
]
STORY = ("Kampung Cireundeu Cimahi", "Warga Kampung Cireundeu dikenal memakai singkong sebagai makanan pokok. "
         "Singkong diolah menjadi rasi, yaitu pengganti nasi, melalui proses penjemuran dan pengukusan yang diwariskan "
         "antargenerasi. Kebiasaan ini menjadi bagian dari identitas kampung dan menarik wisatawan yang ingin belajar "
         "budaya pangan lokal.")


def seed_demo(conn) -> None:
    if conn.execute("SELECT 1 FROM destinations LIMIT 1").fetchone():
        return
    ids = []
    for name, cat, lat, lon, desc, wiki in DEMO:
        cur = conn.execute(
            """INSERT INTO destinations(name,category,description,latitude,longitude,wikipedia_title,status,submitted_by)
               VALUES (?,?,?,?,?,?,'terbit',0)""", (name, cat, desc, lat, lon, wiki))
        ids.append(cur.lastrowid)
        events.publish("DestinasiTerbit", conn, destination_id=cur.lastrowid)
    cur = conn.execute("INSERT INTO stories(title,body,status,author_id) VALUES (?,?, 'terbit', 0)", STORY)
    conn.execute("INSERT INTO story_destinations(story_id,destination_id) VALUES (?,?)", (cur.lastrowid, ids[0]))
    events.publish("CeritaTerbit", conn, story_id=cur.lastrowid, destination_ids=[ids[0]])
    conn.commit()
