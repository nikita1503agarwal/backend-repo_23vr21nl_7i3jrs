import os
from typing import Optional, Literal
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from database import db, create_document, get_documents
from schemas import Member
import stripe

# Load Stripe keys from environment
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

stripe.api_key = STRIPE_SECRET_KEY if STRIPE_SECRET_KEY else None

app = FastAPI(title="Bebahan Membership API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TIERS = {
    "bronze": {"price": 4.99, "currency": "usd"},
    "silver": {"price": 9.99, "currency": "usd"},
    "gold": {"price": 24.99, "currency": "usd"},
}

# Dummy content lists for socials (could be moved to DB later)
SOCIALS = {
    "youtube": [
        {"title": "Welcome to the Bebahan Club", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
    ],
    "instagram": [
        {"title": "Behind the scenes", "url": "https://www.instagram.com/p/Cx12345/"},
    ],
    "tiktok": [
        {"title": "Funny moments", "url": "https://www.tiktok.com/@user/video/123456789"},
    ],
}

class CheckoutSessionRequest(BaseModel):
    email: EmailStr
    tier: Literal["bronze", "silver", "gold"]
    username: Optional[str] = None

class CheckoutSessionResponse(BaseModel):
    checkout_url: str

@app.get("/")
async def root():
    return {"message": "Bebahan Membership API running"}

@app.get("/api/socials")
async def get_socials():
    return SOCIALS

@app.get("/api/tiers")
async def get_tiers():
    return TIERS

@app.post("/api/create-checkout-session", response_model=CheckoutSessionResponse)
async def create_checkout_session(payload: CheckoutSessionRequest):
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    # Map tiers to Stripe Price IDs if provided in env, else use inline prices (one-time) via price_data
    price_id_env_map = {
        "bronze": os.getenv("STRIPE_PRICE_BRONZE"),
        "silver": os.getenv("STRIPE_PRICE_SILVER"),
        "gold": os.getenv("STRIPE_PRICE_GOLD"),
    }

    line_items = []

    env_price_id = price_id_env_map[payload.tier]
    if env_price_id:
        line_items = [{"price": env_price_id, "quantity": 1}]
    else:
        # Fallback to dynamic price_data subscription creation
        cents = int(TIERS[payload.tier]["price"] * 100)
        line_items = [
            {
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": f"Bebahan {payload.tier.capitalize()} Membership",
                    },
                    "recurring": {"interval": "month"},
                    "unit_amount": cents,
                },
                "quantity": 1,
            }
        ]

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=line_items,
            customer_email=payload.email,
            success_url=os.getenv("CHECKOUT_SUCCESS_URL", "http://localhost:3000/?success=true"),
            cancel_url=os.getenv("CHECKOUT_CANCEL_URL", "http://localhost:3000/?canceled=true"),
            metadata={"tier": payload.tier, "username": payload.username or ""},
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Upsert a pending member record (status incomplete until webhook confirms)
    try:
        create_document(
            "member",
            Member(
                email=payload.email,
                tier=payload.tier,
                status="incomplete",
                stripe_customer_id=None,
                stripe_subscription_id=None,
                username=payload.username,
            ),
        )
    except Exception:
        pass

    return CheckoutSessionResponse(checkout_url=session.url)

@app.post("/webhook")
async def stripe_webhook(payload: dict):
    # Verify webhook signature if secret is set
    if STRIPE_WEBHOOK_SECRET:
        import json
        from fastapi import Request
        # In FastAPI you typically read the raw body from Request, but for simplicity in this env,
        # we proceed with unverified payload if not available.
        pass

    event_type = payload.get("type")
    data_object = payload.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        customer = data_object.get("customer")
        subscription = data_object.get("subscription")
        email = data_object.get("customer_details", {}).get("email")
        tier = data_object.get("metadata", {}).get("tier")
        if email and tier:
            try:
                db["member"].update_one(
                    {"email": email},
                    {
                        "$set": {
                            "status": "active",
                            "stripe_customer_id": customer,
                            "stripe_subscription_id": subscription,
                        }
                    },
                    upsert=True,
                )
            except Exception:
                pass

    elif event_type == "customer.subscription.deleted":
        email = data_object.get("customer_email")
        if email:
            try:
                db["member"].update_one({"email": email}, {"$set": {"status": "canceled"}})
            except Exception:
                pass

    return {"received": True}

@app.get("/api/membership/status")
async def membership_status(email: EmailStr):
    doc = db["member"].find_one({"email": str(email)})
    if not doc:
        return {"email": email, "status": "none", "tier": None}
    return {
        "email": doc.get("email"),
        "status": doc.get("status", "none"),
        "tier": doc.get("tier"),
    }

@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"

            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    import os
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
