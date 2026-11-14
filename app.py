
import streamlit as st
import requests
import json
import asyncio
import edge_tts
import os
import re

from PIL import Image
from io import BytesIO
from dotenv import load_dotenv
from google import genai
from google.genai import types

# -----------------------------------
# CONFIGURATION
# -----------------------------------

load_dotenv()

st.set_page_config(
    page_title="AI Museum Audio Guide",
    page_icon="🏛️",
    layout="wide"
)

st.title("🏛️ AI Museum Audio Guide")
st.write(
    "Discover artworks, explore their history "
    "and listen to AI-powered museum narration."
)

st.divider()

# -----------------------------------
# API CLIENT
# -----------------------------------

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    st.error(
        "Gemini API key not found. "
        "Please add it to your .env file."
    )
    st.stop()

client = genai.Client(api_key=API_KEY)


# -----------------------------------
# GEMINI IMAGE ANALYSIS
# -----------------------------------

def analyze_image(image_bytes, mime_type):

    prompt = """
    Analyze this uploaded museum or artwork image.

    Return ONLY valid JSON with these fields:

    {
        "visual_description": "Describe only what is visibly present.",
        "object_type": "Painting, sculpture, artifact, building, etc.",
        "candidate_title": "Possible artwork title or null",
        "candidate_artist": "Possible artist or maker or null",
        "identification_confidence": "High, Medium, or Low",
        "reason": "Brief reason for your identification."
    }

    IMPORTANT:
    - Do not invent artwork names or artists.
    - If you cannot identify the exact artwork, use null.
    - Clearly distinguish visual observations from guesses.
    - Never claim an identification is verified.
    """

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=[
            prompt,
            types.Part.from_bytes(
                data=image_bytes,
                mime_type=mime_type
            )
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2
        )
    )

    return json.loads(response.text)


# -----------------------------------
# ART INSTITUTE OF CHICAGO SEARCH
# -----------------------------------

def search_artic(title):

    url = "https://api.artic.edu/api/v1/artworks/search"

    params = {
        "q": title,
        "limit": 5,
        "fields": "id,title,artist_display,date_display,"
                  "place_of_origin,medium_display,description,"
                  "image_id,is_public_domain"
    }

    try:
        response = requests.get(
            url,
            params=params,
            timeout=20,
            headers={"AIC-User-Agent": "AI-Museum-Audio-Guide"}
        )

        response.raise_for_status()

        data = response.json().get("data", [])

        results = []

        for item in data:

            results.append({
                "museum": "Art Institute of Chicago",
                "title": item.get("title") or "Unknown",
                "artist": item.get("artist_display") or "Unknown",
                "date": item.get("date_display") or "Not available",
                "origin": item.get("place_of_origin") or "Not available",
                "medium": item.get("medium_display") or "Not available",
                "description": item.get("description") or "",
                "image": (
                    "https://www.artic.edu/iiif/2/"
                    + item["image_id"]
                    + "/full/843,/0/default.jpg"
                    if item.get("image_id") else None
                ),
                "url": f"https://www.artic.edu/artworks/{item['id']}"
            })

        return results

    except requests.RequestException:
        return []


# -----------------------------------
# MET MUSEUM SEARCH
# -----------------------------------

def search_met(title):

    url = (
        "https://collectionapi.metmuseum.org/"
        "public/collection/v1.1/search"
    )

    params = {
        "q": title,
        "title": "true",
        "hasImages": "true",
        "limit": 5
    }

    try:
        response = requests.get(
            url,
            params=params,
            timeout=20
        )

        response.raise_for_status()

        object_ids = response.json().get(
            "objectIDs", []
        ) or []

        results = []

        for object_id in object_ids[:5]:

            detail_url = (
                "https://collectionapi.metmuseum.org/"
                f"public/collection/v1/objects/{object_id}"
            )

            detail_response = requests.get(
                detail_url,
                timeout=20
            )

            detail_response.raise_for_status()

            item = detail_response.json()

            results.append({
                "museum": "The Metropolitan Museum of Art",
                "title": item.get("title") or "Unknown",
                "artist": item.get("artistDisplayName") or "Unknown",
                "date": item.get("objectDate") or "Not available",
                "origin": item.get("culture") or "Not available",
                "medium": item.get("medium") or "Not available",
                "description": "",
                "image": item.get("primaryImageSmall"),
                "url": (
                    "https://www.metmuseum.org/art/collection/"
                    f"search/{object_id}"
                )
            })

        return results

    except requests.RequestException:
        return []


# -----------------------------------
# AUDIO GENERATION
# -----------------------------------

async def generate_audio(text):

    speech = edge_tts.Communicate(
        text,
        voice="en-US-AriaNeural"
    )

    await speech.save("museum_audio.mp3")


def clean_description(text):

    if not text:
        return "No additional description is available."

    # Remove HTML tags from museum descriptions
    return re.sub(r"<[^>]*>", "", str(text)).strip()


def make_narration(record):

    description = clean_description(
        record.get("description", "")
    )

    narration = f"""
    Welcome to your museum audio guide.

    You are exploring {record['title']}.

    Artist or creator: {record['artist']}.

    Date of creation: {record['date']}.

    Origin or culture: {record['origin']}.

    Medium: {record['medium']}.

    """

    if description:
        narration += (
            "Museum description: " + description
        )

    narration += (
        "Thank you for exploring this artwork "
        "with your AI Museum Audio Guide."
    )

    return narration


# -----------------------------------
# IMAGE UPLOAD
# -----------------------------------

uploaded_file = st.file_uploader(
    "Upload an artwork or museum object",
    type=["jpg", "jpeg", "png"]
)

if uploaded_file:

    image_bytes = uploaded_file.getvalue()

    mime_type = uploaded_file.type

    image = Image.open(
        BytesIO(image_bytes)
    ).convert("RGB")

    st.image(
        image,
        caption="Your Uploaded Image",
        use_column_width=True
    )

    # --------------------------------
    # ANALYZE IMAGE BUTTON
    # --------------------------------

    if st.button(
        "✨ Analyze Artwork",
        type="primary"
    ):

        try:

            with st.spinner(
                "Gemini AI is analyzing your image..."
            ):

                ai_result = analyze_image(
                    image_bytes,
                    mime_type
                )

            title = ai_result.get(
                "candidate_title"
            )

            if not isinstance(title, str):
                title = ""

            title = title.strip()

            candidates = []

            if title and title.lower() != "null":

                with st.spinner(
                    "Searching museum collections..."
                ):

                    candidates.extend(
                        search_artic(title)
                    )

                    candidates.extend(
                        search_met(title)
                    )

            st.session_state["museum_analysis"] = {
                "ai": ai_result,
                "candidates": candidates,
                "file_name": uploaded_file.name
            }

        except Exception as error:

            st.error("Image analysis failed.")
            st.exception(error)


    # --------------------------------
    # DISPLAY ANALYSIS
    # --------------------------------

    analysis = st.session_state.get(
        "museum_analysis"
    )

    if analysis and analysis["file_name"] == uploaded_file.name:

        ai = analysis["ai"]

        st.divider()

        st.header("🔍 AI Image Analysis")

        st.write(
            ai.get(
                "visual_description",
                "No description available."
            )
        )

        st.write(
            "**Object type:**",
            ai.get("object_type", "Unknown")
        )

        st.write(
            "**Possible artwork title:**",
            ai.get("candidate_title") or "Not identified"
        )

        st.write(
            "**Possible artist:**",
            ai.get("candidate_artist") or "Not identified"
        )

        st.write(
            "**AI confidence:**",
            ai.get("identification_confidence", "Unknown")
        )

        st.caption(
            "AI identification is a suggestion, not verified museum metadata."
        )

        st.divider()

        # --------------------------------
        # MUSEUM DATABASE RESULTS
        # --------------------------------

        st.header("🏛️ Museum Collection Results")

        candidates = analysis["candidates"]

        selected_record = None

        if candidates:

            st.info(
                "These are possible matches based on the AI-suggested "
                "title. They have not been visually verified."
            )

            options = [
                f"{item['title']} — {item['museum']}"
                for item in candidates
            ]

            selected_index = st.selectbox(
                "Select the correct artwork after comparing the details:",
                range(len(options)),
                format_func=lambda i: options[i]
            )

            selected_record = candidates[
                selected_index
            ]

            st.subheader(
                selected_record["title"]
            )

            st.write(
                "**Museum:**",
                selected_record["museum"]
            )

            st.write(
                "**Artist:**",
                selected_record["artist"]
            )

            st.write(
                "**Date:**",
                selected_record["date"]
            )

            st.write(
                "**Origin / Culture:**",
                selected_record["origin"]
            )

            st.write(
                "**Medium:**",
                selected_record["medium"]
            )

            if selected_record["image"]:
                st.image(
                    selected_record["image"],
                    caption="Museum database reference image",
                    width=300
                )

            st.markdown(
                f"[View official museum record]({selected_record['url']})"
            )

            st.warning(
                "Please compare the reference image and details "
                "with your uploaded image before creating narration."
            )

            confirmed = st.checkbox(
                "I confirm that this is the correct artwork."
            )

        else:

            st.warning(
                "No matching record was found in these two museum "
                "collections. The artwork may belong to another "
                "museum or collection."
            )

            confirmed = False

        # --------------------------------
        # AUDIO GUIDE
        # --------------------------------

        st.divider()

        st.header("🎧 Generate Audio Guide")

        if selected_record and confirmed:

            if st.button("🔊 Create Museum Audio"):

                narration = make_narration(
                    selected_record
                )

                try:

                    with st.spinner(
                        "Creating your audio guide..."
                    ):

                        asyncio.run(
                            generate_audio(narration)
                        )

                    st.success(
                        "Your museum audio guide is ready!"
                    )

                    with open(
                        "museum_audio.mp3",
                        "rb"
                    ) as audio_file:

                        audio_bytes = audio_file.read()

                    st.audio(
                        audio_bytes,
                        format="audio/mp3"
                    )

                    st.download_button(
                        "⬇️ Download Audio Guide",
                        data=audio_bytes,
                        file_name="museum_audio.mp3",
                        mime="audio/mpeg"
                    )

                except Exception as error:

                    st.error(
                        "Audio generation failed."
                    )

                    st.exception(error)

        else:

            st.info(
                "Confirm a museum record to generate "
                "a historical audio guide."
            )

st.divider()

st.caption(
    "AI Museum Audio Guide | Gemini AI | Museum APIs | Edge-TTS"
)
