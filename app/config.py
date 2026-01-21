import os
from openai import OpenAI
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")

# OpenAI client
api_key = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=api_key)

# Supabase client
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

# Webhook secret
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")

# Client URL for CORS
CLIENT_URL = os.getenv("CLIENT_URL", "http://localhost:3000")

# Stripe configuration
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_ID_PRO = os.getenv("STRIPE_PRICE_ID_PRO", "")
STRIPE_PRICE_ID_BUSINESS = os.getenv("STRIPE_PRICE_ID_BUSINESS", "")

