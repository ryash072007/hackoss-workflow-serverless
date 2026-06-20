from supabase import create_client

url = "https://hixscnmemqujqgzvfwot.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImhpeHNjbm1lbXF1anFnenZmd290Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njk2NDczNDEsImV4cCI6MjA4NTIyMzM0MX0.flnC0ZwqHNWguCwMwq0S1mLYCc1oeVkqzrzXofYL3cA"  # NOT service_role

supabase = create_client(url, key)

response = supabase.auth.sign_in_with_password({
    "email": "stickmanify@gmail.com",
    "password": "BackendAccess410*"
})

access_token = response.session.access_token

print(access_token)