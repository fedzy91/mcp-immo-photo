"""
Serveur MCP — Retouche Photo Immobilière Guy Hoquet
Déployable sur Render/Railway — partageable via URL
"""
import json, base64, os, sys, asyncio
from typing import Any

# ── MCP SDK ──────────────────────────────────────────────────────────────────
try:
    from mcp.server import Server
    from mcp.server.sse import SseServerTransport
    from mcp.types import Tool, TextContent, ImageContent
    import mcp.types as types
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    print("MCP SDK non installe -- mode test CLI", file=sys.stderr)

# ── FastAPI pour le transport SSE ─────────────────────────────────────────────
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

sys.path.insert(0, os.path.dirname(__file__))
from pipeline import retouch, detect_room_type, get_profile, PROFILES

# ─────────────────────────────────────────────────────────────────────────────
# DÉFINITION DES OUTILS MCP
# ─────────────────────────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "retouch_photo",
        "description": (
            "Retouche automatique d'une photo immobilière pour publication commerciale. "
            "Applique un profil calibré sur 10 paires avant/après réelles : "
            "HDR, balance couleur, luminosité, saturation, netteté, correction distorsion. "
            "Fournir l'image en base64 et le type de pièce pour le meilleur résultat."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "image_base64": {
                    "type": "string",
                    "description": "Image JPEG/PNG encodée en base64"
                },
                "room_type": {
                    "type": "string",
                    "description": "Type de pièce : salon, cuisine, chambre parentale, chambre ado, chambre enfant, chambre bébé, façade, jardin",
                    "default": ""
                },
                "quality": {
                    "type": "integer",
                    "description": "Qualité JPEG sortie (80-97)",
                    "default": 95
                }
            },
            "required": ["image_base64"]
        }
    },
    {
        "name": "analyze_room",
        "description": (
            "Analyse le type de pièce et retourne le profil de retouche recommandé "
            "avec la liste des éléments à supprimer via inpainting IA."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "room_description": {
                    "type": "string",
                    "description": "Description textuelle de la pièce (ex: salon avec canapé, cuisine ouverte...)"
                }
            },
            "required": ["room_description"]
        }
    },
    {
        "name": "list_profiles",
        "description": "Liste tous les profils de retouche disponibles avec leurs paramètres.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
]

# ─────────────────────────────────────────────────────────────────────────────
# LOGIQUE DES OUTILS
# ─────────────────────────────────────────────────────────────────────────────

def handle_retouch_photo(args: dict) -> dict:
    b64   = args.get("image_base64", "")
    room  = args.get("room_type", "")
    qual  = int(args.get("quality", 95))
    if not b64:
        return {"error": "image_base64 est requis"}
    return retouch(b64, room_hint=room, quality=qual)

def handle_analyze_room(args: dict) -> dict:
    desc = args.get("room_description", "")
    room_type = detect_room_type(desc)
    profile   = get_profile(room_type)
    return {
        "room_type": room_type,
        "profile": {k: v for k, v in profile.items() if k != "inpainting_targets"},
        "inpainting_recommended": profile.get("inpainting_targets", []),
        "summary": (
            f"Profil '{room_type}' sélectionné. "
            f"Luminosité \u00d7{profile.get('brightness',1.12):.2f}, "
            f"Saturation \u00d7{profile.get('saturation',0.78):.2f}. "
            f"{len(profile.get('inpainting_targets',[]))} éléments à supprimer par inpainting."
        )
    }

def handle_list_profiles(args: dict) -> dict:
    result = {}
    for name, prof in PROFILES.items():
        if name in ("VERSION", "LEARNED_FROM", "global"):
            continue
        result[name] = {
            "brightness": prof.get("brightness"),
            "saturation": prof.get("saturation"),
            "temperature": prof.get("temperature"),
            "inpainting_targets": prof.get("inpainting_targets", [])
        }
    return {"profiles": result, "total": len(result)}

HANDLERS = {
    "retouch_photo":  handle_retouch_photo,
    "analyze_room":   handle_analyze_room,
    "list_profiles":  handle_list_profiles,
}

# ─────────────────────────────────────────────────────────────────────────────
# SERVEUR HTTP / MCP SSE
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(title="MCP Immo Photo \u2014 Guy Hoquet")

@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0", "profiles": list(k for k in PROFILES if k not in ("VERSION","LEARNED_FROM","global"))}

@app.get("/tools")
async def list_tools():
    return {"tools": TOOLS}

@app.post("/call/{tool_name}")
async def call_tool(tool_name: str, request: Request):
    try:
        body = await request.json()
        if tool_name not in HANDLERS:
            return JSONResponse({"error": f"Outil inconnu: {tool_name}"}, status_code=404)
        result = HANDLERS[tool_name](body)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# \u2500\u2500 Point d'entr\u00e9e MCP SSE standard (pour Claude.ai connecteurs) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
if MCP_AVAILABLE:
    mcp_server = Server("immo-photo-retouche")
    sse_transport = SseServerTransport("/mcp")

    @app.get("/mcp")
    async def mcp_sse(request: Request):
        async with sse_transport.connect_sse(request.scope, request.receive, request._send) as streams:
            await mcp_server.run(streams[0], streams[1], mcp_server.create_initialization_options())

    @mcp_server.list_tools()
    async def mcp_list_tools():
        return [types.Tool(name=t["name"], description=t["description"], inputSchema=t["inputSchema"]) for t in TOOLS]

    @mcp_server.call_tool()
    async def mcp_call_tool(name: str, arguments: dict) -> list:
        result = HANDLERS.get(name, lambda _: {"error": "Outil inconnu"})(arguments)
        if "image_base64" in result and result.get("success"):
            return [
                types.TextContent(type="text", text=json.dumps({k:v for k,v in result.items() if k != "image_base64"})),
                types.ImageContent(type="image", data=result["image_base64"], mimeType="image/jpeg")
            ]
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"Serveur MCP Immo Photo demarre sur port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
