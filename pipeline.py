"""
Pipeline de retouche photo immobilière Guy Hoquet
Calibré sur 10 paires avant/après réelles
"""
import cv2
import numpy as np
from PIL import Image, ImageEnhance
import base64
import io
import json
import os

PROFILES_PATH = os.path.join(os.path.dirname(__file__), "profiles.json")
with open(PROFILES_PATH) as f:
    PROFILES = json.load(f)

ROOM_KEYWORDS = {
    "salon": "salon_salle_manger", "séjour": "salon_sejour",
    "salle à manger": "salon_salle_manger", "living": "salon_sejour",
    "cuisine": "cuisine", "kitchen": "cuisine",
    "chambre parentale": "chambre_parentale", "chambre principale": "chambre_parentale",
    "master": "chambre_parentale",
    "chambre ado": "chambre_ado", "chambre adolescent": "chambre_ado",
    "chambre enfant": "chambre_enfant", "chambre bébé": "chambre_bebe",
    "bébé": "chambre_bebe", "nursery": "chambre_bebe",
    "façade": "facade_exterieure", "extérieur": "facade_exterieure",
    "jardin": "jardin", "garden": "jardin",
}

def detect_room_type(room_hint: str = "") -> str:
    if room_hint:
        hint_lower = room_hint.lower()
        for kw, profile in ROOM_KEYWORDS.items():
            if kw in hint_lower:
                return profile
    return "default"

def get_profile(room_type: str) -> dict:
    return PROFILES.get(room_type, PROFILES["default"])

def decode_image(b64: str) -> np.ndarray:
    data = base64.b64decode(b64)
    arr  = np.frombuffer(data, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)

def encode_image(img: np.ndarray, quality: int = 95) -> str:
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return base64.b64encode(buf).decode()

def apply_profile(img: np.ndarray, profile: dict, global_cfg: dict) -> np.ndarray:
    h, w = img.shape[:2]

    # 1. RECADRAGE GLOBAL
    cl = int(w * global_cfg.get("crop_left_pct", 0.02))
    cr = int(w * global_cfg.get("crop_right_pct", 0.01))
    img = img[:, cl:w-cr]
    h, w = img.shape[:2]

    # 2. HDR LOCAL
    if profile.get("hdr", True):
        img_f = img.astype(np.float32) / 255.0
        gray  = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        bm = np.clip((gray - 0.72) / 0.22, 0, 1)
        dm = np.clip((0.38 - gray) / 0.22, 0, 1)
        bm3 = np.stack([bm]*3, axis=2)
        dm3 = np.stack([dm]*3, axis=2)
        img_f = np.clip(img_f - bm3*0.25 + dm3*0.18, 0, 1)
        img = (img_f * 255).astype(np.uint8)

    # 3. TEMPERATURE
    temp = profile.get("temperature", global_cfg.get("temperature_shift", -10))
    if abs(temp) > 0:
        img_f = img.astype(np.float32)
        if temp < 0:  # refroidir
            img_f[:,:,2] = np.clip(img_f[:,:,2] * (1 + temp/300), 0, 255)
            img_f[:,:,0] = np.clip(img_f[:,:,0] * (1 - temp/300), 0, 255)
        else:  # réchauffer
            img_f[:,:,2] = np.clip(img_f[:,:,2] * (1 + temp/200), 0, 255)
            img_f[:,:,0] = np.clip(img_f[:,:,0] * (1 - temp/200), 0, 255)
        img = img_f.astype(np.uint8)

    # 4. SHADOWS LIFT
    shadows = profile.get("shadows", global_cfg.get("lift_blacks", 14))
    if shadows > 0:
        img_f = img.astype(np.float32)
        gray_f = (img_f[:,:,0]*0.114 + img_f[:,:,1]*0.587 + img_f[:,:,2]*0.299) / 255.0
        boost = shadows * np.maximum(0, 1 - gray_f * 2.5)
        for c in range(3):
            img_f[:,:,c] = np.clip(img_f[:,:,c] + boost, 0, 255)
        img = img_f.astype(np.uint8)

    # 5. HIGHLIGHTS RECOVERY
    hl = profile.get("highlights", -0.12)
    if hl < 0:
        img_f = img.astype(np.float32)
        gray_f = (img_f[:,:,0]*0.114 + img_f[:,:,1]*0.587 + img_f[:,:,2]*0.299) / 255.0
        reduce = hl * np.maximum(0, gray_f * 2 - 1)
        for c in range(3):
            img_f[:,:,c] = np.clip(img_f[:,:,c] + reduce * 255, 0, 255)
        img = img_f.astype(np.uint8)

    # 6. PIL : brightness, contrast, saturation
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    pil = ImageEnhance.Brightness(pil).enhance(profile.get("brightness", 1.12))
    pil = ImageEnhance.Contrast(pil).enhance(profile.get("contrast", 1.12))
    pil = ImageEnhance.Color(pil).enhance(profile.get("saturation", 0.78))

    # 7. CLARITY / MICROCONTRASTE
    clarity = profile.get("clarity", 0.3)
    if clarity > 0:
        img_cv = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        orig = img_cv.copy()
        blur = cv2.GaussianBlur(img_cv, (0,0), 8)
        img_cv = np.clip(orig + (orig.astype(np.float32) - blur.astype(np.float32)) * clarity, 0, 255).astype(np.uint8)
        pil = Image.fromarray(cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB))

    # 8. SHARPEN
    pil = ImageEnhance.Sharpness(pil).enhance(global_cfg.get("sharpen", 1.6))

    # 9. DÉBRUITAGE
    img_cv = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    img_cv = cv2.bilateralFilter(img_cv, 7, 55, 55)

    # 10. LIFT NOIRS FINAL
    img_cv = img_cv.astype(np.float32)
    lift = global_cfg.get("lift_blacks", 14)
    img_cv = np.clip(img_cv * (1 - lift/255) + lift, 0, 255).astype(np.uint8)

    # 11. VIGNETTAGE
    vs = global_cfg.get("vignette_strength", 0.18)
    hv, wv = img_cv.shape[:2]
    cx, cy = wv/2, hv/2
    maxD = np.sqrt(cx**2 + cy**2)
    Y, X  = np.mgrid[0:hv, 0:wv]
    dist  = np.sqrt((X-cx)**2 + (Y-cy)**2) / maxD
    vign  = 1 - vs * np.maximum(0, (dist - 0.72) / (1 - 0.72))
    for c in range(3):
        img_cv[:,:,c] = np.clip(img_cv[:,:,c] * vign, 0, 255).astype(np.uint8)

    # 12. CORRECTION DISTORSION SMARTPHONE
    f  = wv * 0.88
    K  = np.array([[f,0,wv/2],[0,f,hv/2],[0,0,1]], dtype=np.float32)
    D  = np.array([-0.06, 0.03, 0, 0], dtype=np.float32)
    img_cv = cv2.undistort(img_cv, K, D)

    # 13. RESIZE SORTIE 2400px max
    target_w = 2400
    if img_cv.shape[1] > target_w:
        th = int(img_cv.shape[0] * target_w / img_cv.shape[1])
        img_cv = cv2.resize(img_cv, (target_w, th), interpolation=cv2.INTER_LANCZOS4)

    return img_cv

def retouch(b64_input: str, room_hint: str = "", quality: int = 95) -> dict:
    """
    Entrée  : image base64, type de pièce (optionnel)
    Sortie  : dict avec image retouchée base64 + métadonnées
    """
    img = decode_image(b64_input)
    if img is None:
        return {"error": "Impossible de décoder l'image"}

    room_type = detect_room_type(room_hint)
    profile   = get_profile(room_type)
    global_cfg = PROFILES["global"]

    result = apply_profile(img, profile, global_cfg)
    b64_out = encode_image(result, quality)

    return {
        "success": True,
        "room_type_detected": room_type,
        "profile_used": profile,
        "inpainting_recommended": profile.get("inpainting_targets", []),
        "output_size": f"{result.shape[1]}x{result.shape[0]}",
        "image_base64": b64_out,
        "message": f"Retouche appliquée — profil '{room_type}'. {len(profile.get('inpainting_targets', []))} éléments nécessitent un inpainting IA supplémentaire."
    }
