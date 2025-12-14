import streamlit as st
import pandas as pd
import google.generativeai as genai
import time
import os
import random

# --- CONFIGURATION ---
DATA_FILE = "reviews_db.csv"

# --- AUTHENTICATION (Cloud) ---
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    # Fallback for local testing if you haven't set secrets yet
    # You can remove this 'else' block once deployed
    pass 

def get_gemini_response(prompt):
    try:
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error: {str(e)}"

# --- DATA HANDLING ---
def init_db():
    if not os.path.exists(DATA_FILE):
        df = pd.DataFrame(columns=[
            "timestamp", "rating", "review_text", 
            "ai_reply", "ai_summary", "ai_action", 
            "user_name", "avatar"
        ])
        df.to_csv(DATA_FILE, index=False)

def load_data():
    if os.path.exists(DATA_FILE):
        return pd.read_csv(DATA_FILE)
    return pd.DataFrame()

def save_entry(rating, text, reply, summary, action):
    df = load_data()
    fake_names = ["Alex R.", "Sam K.", "Jordan P.", "Casey M.", "Taylor S.", "Priya D.", "Rohan G."]
    fake_avatars = ["🐶", "🐱", "🦊", "🐻", "🐼", "🐨", "🐯"]
    
    new_entry = pd.DataFrame([{
        "timestamp": time.strftime("%Y-%m-%d"), 
        "rating": rating,
        "review_text": text,
        "ai_reply": reply,
        "ai_summary": summary,
        "ai_action": action,
        "user_name": random.choice(fake_names),
        "avatar": random.choice(fake_avatars)
    }])
    df = pd.concat([df, new_entry], ignore_index=True)
    df.to_csv(DATA_FILE, index=False)

# --- AI GENERATION ---
def generate_ai_content(review_text, rating):
    # 1. User Reply
    reply_prompt = f"""
    You are a business owner replying to a customer review. 
    Review: "{review_text}" (Rating: {rating}/5).
    Write a short, professional, and grateful response. Max 2 sentences.
    """
    reply = get_gemini_response(reply_prompt)

    # 2. Admin Summary & Action
    admin_prompt = f"""
    Analyze this review: "{review_text}" (Rating: {rating}/5).
    1. Summarize key point in 5 words.
    2. Suggest one specific business action.
    
    Format:
    Summary: <text>
    Action: <text>
    """
    analysis = get_gemini_response(admin_prompt)
    
    try:
        lines = analysis.split('\n')
        summary = next((line.split(': ')[1] for line in lines if 'Summary:' in line), "General Feedback")
        action = next((line.split(': ')[1] for line in lines if 'Action:' in line), "Review Manually")
    except:
        summary = "Analysis Pending"
        action = "Review Manually"

    return reply, summary, action

# --- MAIN APP UI ---
st.set_page_config(page_title="Fynd Reviews", layout="wide")
init_db()

st.title("🚀 Fynd Dashboard")

tab_user, tab_admin = st.tabs(["⭐ Public Reviews", "🛡️ Admin Dashboard"])

# === DASHBOARD 1: GOOGLE REVIEWS STYLE ===
with tab_user:
    col_left, col_right = st.columns([1, 2])
    
    with col_left:
        st.subheader("Rate your experience")
        with st.form("user_form"):
            # --- CHANGED: SLIDER TO CLICKABLE STARS ---
            st.write("Click to rate:")
            rating_input = st.feedback("stars")
            
            # Logic: st.feedback returns 0,1,2,3,4. We need 1-5.
            # If user doesn't click, we default to 5.
            stars = (rating_input + 1) if rating_input is not None else 5
            
            review = st.text_area("Share details of your own experience")
            submitted = st.form_submit_button("Post Review")
            
            if submitted and review:
                with st.spinner("Posting..."):
                    reply, summary, action = generate_ai_content(review, stars)
                    save_entry(stars, review, reply, summary, action)
                    st.success("Thanks for sharing!")
                    time.sleep(1)
                    st.rerun()

    with col_right:
        data = load_data()
        if not data.empty:
            avg_rating = data['rating'].mean()
            st.markdown(f"### {avg_rating:.1f} ⭐⭐⭐⭐⭐ ({len(data)} reviews)")
            st.divider()
            
            for index, row in data.sort_index(ascending=False).iterrows():
                c1, c2 = st.columns([1, 10])
                with c1: st.markdown(f"## {row['avatar']}")
                with c2:
                    st.markdown(f"**{row['user_name']}** &nbsp; <span style='color:grey'>{row['timestamp']}</span>", unsafe_allow_html=True)
                    st.markdown(f"{'⭐' * int(row['rating'])}")
                    st.write(row['review_text'])
                    if pd.notna(row['ai_reply']):
                        st.info(f"**Response from the owner:**\n\n{row['ai_reply']}")
                    st.divider()
        else:
            st.info("No reviews yet.")

# === DASHBOARD 2: ADMIN VIEW ===
with tab_admin:
    st.header("Internal Feedback Monitor")
    if st.button("🔄 Refresh Admin Data"): st.rerun()
    data = load_data()
    if not data.empty:
        st.dataframe(data.sort_index(ascending=False), use_container_width=True)
    else:
        st.info("No reviews found.")