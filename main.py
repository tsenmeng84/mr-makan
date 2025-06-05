import discord
from discord.ext import commands
import json
import os
import aiohttp
import openai
from bs4 import BeautifulSoup
from uuid import uuid4
from dotenv import load_dotenv
import subprocess

load_dotenv()

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)
openai.api_key = os.getenv("OPENAI_KEY")

RECOMMEND_FILE = 'recommend.json'
CUISINE_FILE = 'cuisines.json'
RANKS_FILE = 'ranks.json'
IMAGE_DIR = 'static/images'
DEFAULT_IMG = 'default.png'
MAX_HISTORY = 20
history = []

def load_json(file, default):
    if not os.path.exists(file):
        with open(file, 'w') as f:
            json.dump(default, f)
    with open(file) as f:
        return json.load(f)

def save_json(file, data):
    with open(file, 'w') as f:
        json.dump(data, f, indent=2)

recommend_data = load_json(RECOMMEND_FILE, [])
cuisines = load_json(CUISINE_FILE, {
    "1": "Chinese", "2": "Indian", "3": "Malay", "4": "Western/Cafe",
    "5": "Steakhouse", "6": "Italian", "7": "French", "8": "Fish 'n' Chips",
    "9": "Mexican", "10": "Thai", "11": "Indonesian", "12": "Vietnamese", "13": "Others"
})
ranks = load_json(RANKS_FILE, {})

RANK_NAMES = [
    (36, 'Michelin Inspector'),
    (26, 'Food Critique'),
    (16, 'Master Foodie'),
    (6, 'Senior Foodie'),
    (0, 'Foodie')
]

def get_rank(points):
    for threshold, title in RANK_NAMES:
        if points >= threshold:
            return title

@bot.command(name='help')
async def help_command(ctx):
    help_text = """
**Mr. Makan Bot Commands 🍜**

`!ask` – Ask any food/cooking question. Mr. Makan will reply using his wisdom (GPT-powered).  
`!recommend` – Add a food recommendation. Mr. Makan will guide you step-by-step.  
`!viewall` – View all stored recommendations.  
`!view <cuisine>` – View only specific cuisine recommendations (e.g., `!view chinese`).  
`!viewweb` – Get a webpage version of all recommendations.  
`!edit` – Edit or delete a previous recommendation using its ID.  
`!rank` – View your rank and the leaderboard.
"""
    await ctx.send(help_text)

@bot.command(name='rank')
async def rank_command(ctx):
    user_ranks = [(uid, data["points"]) for uid, data in ranks.items()]
    sorted_ranks = sorted(user_ranks, key=lambda x: x[1], reverse=True)

    leaderboard = "**🍽️ Leaderboard 🍽️**\n"
    for i, (uid, points) in enumerate(sorted_ranks, 1):
        user = await bot.fetch_user(int(uid))
        title = get_rank(points)
        leaderboard += f"{i}. {title} {user.name} – {points} points\n"

    user_id = str(ctx.author.id)
    points = ranks.get(user_id, {}).get("points", 0)
    rank_title = get_rank(points)
    await ctx.send(f"{rank_title} {ctx.author.name}, you have {points} points.\n\n{leaderboard}")

@bot.command(name='recommend')
async def recommend(ctx):
    user_id = str(ctx.author.id)
    user_name = ctx.author.name
    await ctx.send(f"{get_rank(ranks.get(user_id, {}).get('points', 0))} {user_name}, let’s make a new recommendation!\nStep 1️⃣: Send the restaurant URL.")

    def check(m): return m.author == ctx.author and m.channel == ctx.channel
    try:
        msg = await bot.wait_for('message', timeout=120.0, check=check)
        url = msg.content.strip()

        # Step 2: Try to fetch the title
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                html = await resp.text()
                soup = BeautifulSoup(html, 'html.parser')
                title_tag = soup.find('title')
                suggested_name = title_tag.text.strip() if title_tag else "Unknown"
        await ctx.send(f"Step 2️⃣: I found this name from the URL: **{suggested_name}**. Is this correct? (yes/no)")

        msg = await bot.wait_for('message', timeout=60.0, check=check)
        if msg.content.lower() != 'yes':
            await ctx.send("Please provide the correct name:")
            msg = await bot.wait_for('message', timeout=60.0, check=check)
            name = msg.content.strip()
        else:
            name = suggested_name

        # Step 3: Cuisine Type
        cuisine_msg = "**Step 3️⃣: Choose the cuisine type by number:**\n"
        for k, v in cuisines.items():
            cuisine_msg += f"{k}. {v}\n"
        await ctx.send(cuisine_msg)

        msg = await bot.wait_for('message', timeout=60.0, check=check)
        cuisine_choice = msg.content.strip()
        cuisine = cuisines.get(cuisine_choice, "Others")
        if cuisine == "Others":
            await ctx.send("Please enter the cuisine type:")
            msg = await bot.wait_for('message', timeout=60.0, check=check)
            cuisine = msg.content.strip()
            max_id = max(map(int, cuisines.keys()))
            cuisines[str(max_id + 1)] = cuisine
            save_json(CUISINE_FILE, cuisines)

        # Step 4: Rating
        await ctx.send("Step 4️⃣: Rate this place out of 10 (0 if not tried):")
        msg = await bot.wait_for('message', timeout=60.0, check=check)
        rating = float(msg.content.strip())

        # Step 5: Image
        await ctx.send("Step 5️⃣: Upload one picture from the restaurant.")
        msg = await bot.wait_for('message', timeout=120.0, check=check)
        if msg.attachments:
            attachment = msg.attachments[0]
            ext = os.path.splitext(attachment.filename)[1]
            img_id = str(uuid4()) + ext
            img_path = os.path.join(IMAGE_DIR, img_id)
            await attachment.save(img_path)
        else:
            img_id = DEFAULT_IMG

        review = ""
        if rating > 0:
            await ctx.send("Step 6️⃣: Would you like to answer a short review now? (yes/no)")
            msg = await bot.wait_for('message', timeout=60.0, check=check)
            if msg.content.lower() == "yes":
                questions = [
                    "What did you or your party eat?",
                    "Favourite dish and why?",
                    "Least favourite dish and why?",
                    "Ambience?",
                    "Price thoughts?",
                    "Will you return?",
                    "Any other comments?"
                ]
                answers = []
                for q in questions:
                    await ctx.send(q)
                    msg = await bot.wait_for('message', timeout=90.0, check=check)
                    answers.append(msg.content.strip())

                # Generate summary review
                summary_prompt = f"""Summarise this review in 50 words like a food critic:
                {' | '.join(answers)}"""
                response = openai.ChatCompletion.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": summary_prompt}],
                    max_tokens=100
                )
                review = response.choices[0].message.content.strip()
                ranks.setdefault(user_id, {"points": 0})
                ranks[user_id]["points"] += 3
            else:
                review = ""

        # Finalize recommendation
        entry_id = len(recommend_data) + 1
        recommend_data.append({
            "id": entry_id,
            "url": url,
            "name": name,
            "cuisine": cuisine,
            "rating": rating,
            "review": review,
            "user": user_name,
            "image": img_id
        })
        ranks.setdefault(user_id, {"points": 0})
        ranks[user_id]["points"] += 1

        save_json(RECOMMEND_FILE, recommend_data)
        save_json(RANKS_FILE, ranks)
        await ctx.send(f"Thanks {get_rank(ranks[user_id]['points'])} {user_name}! Your recommendation has been saved. ✅")

    except Exception as e:
        await ctx.send(f"Something went wrong: {e}")

@bot.command(name='ask')
async def ask_command(ctx, *, question):
    user_id = str(ctx.author.id)
    user_name = ctx.author.name

    # Update chat history
    history.append({"role": "user", "content": question})
    if len(history) > 20:
        history.pop(0)

    # Context from recommendations
    context_info = "Here are some recommendations:\n"
    for entry in recommend_data[-5:]:  # last 5 recommendations
        context_info += f"- {entry['name']} ({entry['cuisine']}), Rating: {entry['rating']}/10. {entry.get('review', '')}\n"

    system_prompt = f"You are Mr. Makan, a Malaysian foodie and cooking enthusiast. Use the recommendations and reviews below to help answer:\n{context_info}"

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt}
            ] + history,
            max_tokens=250
        )
        answer = response.choices[0].message.content.strip()
        history.append({"role": "assistant", "content": answer})

        await ctx.send(f"{get_rank(ranks.get(user_id, {}).get('points', 0))} {user_name}, here's what I think:\n{answer}")
    except Exception as e:
        await ctx.send(f"Sorry, something went wrong while answering: {e}")

@bot.command(name='viewall')
async def view_all(ctx):
    if not recommend_data:
        await ctx.send("No recommendations yet 😢")
        return

    msg = "**All Recommendations:**\n"
    for entry in recommend_data:
        msg += f"ID {entry['id']}: [{entry['name']}]({entry['url']}) | Cuisine: {entry['cuisine']} | Rating: {entry['rating']}/10\n"
    await ctx.send(msg)

@bot.command(name='view')
async def view_cuisine(ctx, *, cuisine):
    found = [entry for entry in recommend_data if entry['cuisine'].lower() == cuisine.lower()]
    if not found:
        await ctx.send(f"No recommendations for **{cuisine}** cuisine.")
        return

    msg = f"**Recommendations for {cuisine.capitalize()}:**\n"
    for entry in found:
        msg += f"ID {entry['id']}: [{entry['name']}]({entry['url']}) | Rating: {entry['rating']}/10\n"
    await ctx.send(msg)

@bot.command(name='viewweb')
async def view_web(ctx):
    try:
        items_html = ""
        for entry in recommend_data:
            img_file = entry['image'] if entry['image'] != "" else DEFAULT_IMG
            items_html += f"""
            <div class="card">
                <img src="images/{img_file}" alt="{entry['name']}">
                <div class="info">
                    <h2><a href="{entry['url']}" target="_blank">{entry['name']}</a></h2>
                    <p>{entry['cuisine']} – Rating: {entry['rating']}/10</p>
                    <p>{entry.get('review', '')}</p>
                </div>
            </div>
            """

        html_prompt = f"""
Generate a dark-themed HTML page using Yelp-style cards titled "Mr. Makan Food Recommendations".
Only include the HTML without any comments or markdown.
Use this content block:
{items_html}
"""

        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": html_prompt}],
            max_tokens=1500
        )
        html_code = response.choices[0].message.content.strip()

        with open("static/index.html", "w", encoding="utf-8") as f:
            f.write(html_code)

        await ctx.send("Webpage updated! View it on GitHub Pages.")
    except Exception as e:
        await ctx.send(f"Failed to generate webpage: {e}")

    def push_to_github():
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", "Update recommendations page"], check=True)
        subprocess.run(["git", "push"], check=True)
    except subprocess.CalledProcessError as e:
        print("Git push failed:", e)

@bot.command(name='edit')
async def edit_command(ctx):
    await ctx.send("Please enter the ID of the recommendation you want to edit/delete:")

    def check(m): return m.author == ctx.author and m.channel == ctx.channel
    try:
        msg = await bot.wait_for('message', timeout=60.0, check=check)
        entry_id = int(msg.content)
        entry = next((e for e in recommend_data if e['id'] == entry_id), None)

        if not entry:
            await ctx.send("Invalid ID.")
            return

        await ctx.send(f"What do you want to edit?\n1. URL\n2. Name\n3. Cuisine\n4. Rating\n5. Write new review\n6. Delete")

        msg = await bot.wait_for('message', timeout=60.0, check=check)
        choice = msg.content.strip()

        if choice == "1":
            await ctx.send("Enter new URL:")
            msg = await bot.wait_for('message', timeout=60.0, check=check)
            entry['url'] = msg.content.strip()
        elif choice == "2":
            await ctx.send("Enter new name:")
            msg = await bot.wait_for('message', timeout=60.0, check=check)
            entry['name'] = msg.content.strip()
        elif choice == "3":
            await ctx.send("Enter new cuisine:")
            msg = await bot.wait_for('message', timeout=60.0, check=check)
            entry['cuisine'] = msg.content.strip()
        elif choice == "4":
            await ctx.send("Enter new rating out of 10:")
            msg = await bot.wait_for('message', timeout=60.0, check=check)
            entry['rating'] = float(msg.content.strip())
        elif choice == "5":
            await ctx.send("Enter new review:")
            msg = await bot.wait_for('message', timeout=120.0, check=check)
            review_input = msg.content.strip()

            response = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[{
                    "role": "user",
                    "content": f"Summarize the following in 50 words as a food critic:\n{review_input}"
                }],
                max_tokens=100
            )
            entry['review'] = response.choices[0].message.content.strip()
        elif choice == "6":
            recommend_data.remove(entry)
            await ctx.send("Recommendation deleted.")
        else:
            await ctx.send("Invalid choice.")
            return

        save_json(RECOMMEND_FILE, recommend_data)
        await ctx.send("Entry updated.")
    except Exception as e:
        await ctx.send(f"Edit failed: {e}")

@bot.event
async def on_ready():
    print(f"Mr. Makan is online as {bot.user} 🍛")
