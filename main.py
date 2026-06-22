from fastapi import FastAPI, Request, Query, Form, UploadFile, File
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from database import engine, SessionLocal, Base
from models import Recipe
from sqlalchemy import or_

import json
import os
import shutil
from dotenv import load_dotenv
from google import genai
from google.genai import errors


app = FastAPI(title="עוגות קרם")

Base.metadata.create_all(bind=engine)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

load_dotenv()

gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def get_unique_image_filename(upload_dir: str, filename: str):
    name, extension = os.path.splitext(
        filename.replace(" ", "_")
    )

    candidate = f"{name}{extension}"
    counter = 1

    while os.path.exists(
        os.path.join(upload_dir, candidate)
    ):
        candidate = (
            f"{name}_{counter}{extension}"
        )
        counter += 1

    return candidate


def save_uploaded_image(
    image_file: UploadFile | None
):
    if not image_file or not image_file.filename:
        return ""

    upload_dir = "static/images/recipes"
    os.makedirs(upload_dir, exist_ok=True)

    safe_filename = get_unique_image_filename(
        upload_dir,
        image_file.filename
    )

    file_path = os.path.join(
        upload_dir,
        safe_filename
    )

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(
            image_file.file,
            buffer
        )

    return (
        f"/static/images/recipes/"
        f"{safe_filename}"
    )


def get_recipe_images():
    images_dir = "static/images/recipes"

    if not os.path.exists(images_dir):
        return []

    allowed_extensions = [".jpg", ".jpeg", ".png", ".webp"]

    images = []

    for filename in os.listdir(images_dir):
        if os.path.splitext(filename)[1].lower() in allowed_extensions:
            images.append(f"/static/images/recipes/{filename}")

    return images

def get_recipe_images_with_usage():
    images = get_recipe_images()

    db = get_db()

    used_images = {
        recipe.image_url
        for recipe in db.query(Recipe).all()
        if recipe.image_url
    }

    db.close()

    result = []

    for image in images:
        result.append({
            "url": image,
            "is_used": image in used_images,
        })

    return result

def get_db():
    db = SessionLocal()
    try:
        return db
    finally:
        pass


@app.get("/")
def home(
    request: Request,
    q: str = Query(default=""),
    mode: str = Query(default="and"),
):
    db = get_db()

    query = db.query(Recipe)

    if q:
        search_words = q.split()

        if mode == "or":
            filters = []

            for word in search_words:
                search = f"%{word}%"

                filters.append(
                    (Recipe.title.like(search))
                    | (Recipe.category.like(search))
                    | (Recipe.description.like(search))
                    | (Recipe.tags.like(search))
                    | (Recipe.ingredients.like(search))
                    | (Recipe.instructions.like(search))
                )

            query = query.filter(or_(*filters))

        else:
            for word in search_words:
                search = f"%{word}%"

                query = query.filter(
                    (Recipe.title.like(search))
                    | (Recipe.category.like(search))
                    | (Recipe.description.like(search))
                    | (Recipe.tags.like(search))
                    | (Recipe.ingredients.like(search))
                    | (Recipe.instructions.like(search))
                )

    recipes = query.order_by(Recipe.id.desc()).all()
    db.close()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "recipes": recipes,
            "q": q,
            "mode": mode,
            "total_recipes": len(recipes),
        },
    )


@app.get("/recipe/{recipe_id}")
def recipe_page(request: Request, recipe_id: int):
    db = get_db()
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    db.close()

    return templates.TemplateResponse(
        request=request,
        name="recipe.html",
        context={"recipe": recipe},
    )


@app.get("/admin")
def admin_page(
    request: Request,
    selected_image: str = "",
    picker_cancel: str = "",
):
    db = get_db()
    recipes = db.query(Recipe).order_by(Recipe.id.desc()).all()
    db.close()

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "recipes": recipes,
            "recipe_images": get_recipe_images(),
            "selected_image": selected_image,
            "picker_cancel": picker_cancel,
        },
    )


@app.get("/image-picker")
def image_picker_page(request: Request, return_to: str = "/admin"):
    recipe_images = get_recipe_images_with_usage()
    
    return templates.TemplateResponse(
        request=request,
        name="image_picker.html",
        context={
            "recipe_images": recipe_images,
            "return_to": return_to,
        },
    )


@app.get("/ai-search")
def ai_search_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="ai_search.html",
        context={},
    )


@app.post("/ai-search")
def ai_search(request: Request, user_request: str = Form(...)):
    prompt = f"""
אתה עוזר מומחה לעוגות וקינוחים.

המשתמש כתב:
{user_request}

הצע 3 מתכונים חדשים שמתאימים לבקשה.

החזר JSON בלבד, בלי הסברים ובלי Markdown.

המבנה המדויק:

[
  {{
    "title": "שם המתכון",
    "category": "קטגוריה",
    "description": "תיאור קצר",
    "image_url": "קישור לתמונה מתאימה או מחרוזת ריקה אם אין",
    "ingredients": "מרכיב 1\\nמרכיב 2\\nמרכיב 3",
    "instructions": "שלב 1\\nשלב 2\\nשלב 3",
    "rating": 4.5,
    "difficulty": "קל",
    "cost": "בינוני",
    "prep_time": "30 דקות",
    "tags": "שוקולד, ללא אפייה, קינוח"
  }}
]

חשוב:
- כתוב בעברית.
- עוגות וקינוחים בלבד.
- החזר רק JSON תקין.
- אל תוסיף טקסט לפני או אחרי ה-JSON.
- אם אינך בטוח לגבי קישור תמונה אמיתי, החזר image_url ריק.
"""

    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )

        ai_answer = response.text.strip()

        try:
            ai_recipes = json.loads(ai_answer)
            ai_answer = ""
        except json.JSONDecodeError:
            ai_recipes = []

    except errors.ClientError:
        ai_answer = "חרגת זמנית ממכסת השימוש של Gemini. נסה שוב בעוד דקה."
        ai_recipes = []

    return templates.TemplateResponse(
        request=request,
        name="ai_search.html",
        context={
            "user_request": user_request,
            "ai_answer": ai_answer,
            "ai_recipes": ai_recipes,
        },
    )


@app.post("/admin/add")
def add_recipe(
    title: str = Form(...),
    category: str = Form(...),
    description: str = Form(...),
    image_url: str = Form(""),
    image_file: UploadFile | None = File(None),
    ingredients: str = Form(""),
    instructions: str = Form(""),
    rating: float = Form(...),
    difficulty: str = Form(...),
    cost: str = Form(...),
    prep_time: str = Form(...),
    tags: str = Form(""),
    created_by: str = Form("Nir"),
):
    db = get_db()

    uploaded_image_url = save_uploaded_image(image_file)
    final_image_url = uploaded_image_url if uploaded_image_url else image_url

    recipe = Recipe(
        title=title,
        category=category,
        description=description,
        image_url=final_image_url,
        ingredients=ingredients,
        instructions=instructions,
        rating=rating,
        difficulty=difficulty,
        cost=cost,
        prep_time=prep_time,
        tags=tags,
        source="manual",
        source_url="",
        created_by=created_by,
    )

    db.add(recipe)
    db.commit()
    db.close()

    return RedirectResponse(url="/admin", status_code=303)


@app.post("/delete/{recipe_id}")
def delete_recipe(recipe_id: int):
    db = get_db()

    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()

    if recipe:
        db.delete(recipe)
        db.commit()

    db.close()

    return RedirectResponse(url="/", status_code=303)


@app.get("/edit/{recipe_id}")
def edit_recipe_page(
    request: Request,
    recipe_id: int,
    selected_image: str = "",
    picker_cancel: str = "",
):
    db = get_db()

    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()

    db.close()

    if not recipe:
        return RedirectResponse(url="/admin", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="edit.html",
        context={
            "recipe": recipe,
            "recipe_images": get_recipe_images(),
            "selected_image": selected_image,
            "picker_cancel": picker_cancel,
        },
    )


@app.post("/edit/{recipe_id}")
def edit_recipe(
    recipe_id: int,
    title: str = Form(...),
    category: str = Form(...),
    description: str = Form(...),
    image_url: str = Form(""),
    image_file: UploadFile | None = File(None),
    ingredients: str = Form(""),
    instructions: str = Form(""),
    rating: float = Form(...),
    difficulty: str = Form(...),
    cost: str = Form(...),
    prep_time: str = Form(...),
    tags: str = Form(""),
    created_by: str = Form("Nir"),
):
    db = get_db()

    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()

    uploaded_image_url = save_uploaded_image(image_file)
    final_image_url = uploaded_image_url if uploaded_image_url else image_url

    if recipe:
        recipe.title = title
        recipe.category = category
        recipe.description = description
        recipe.image_url = final_image_url
        recipe.ingredients = ingredients
        recipe.instructions = instructions
        recipe.rating = rating
        recipe.difficulty = difficulty
        recipe.cost = cost
        recipe.prep_time = prep_time
        recipe.tags = tags
        recipe.created_by = created_by

        db.commit()

    db.close()

    return RedirectResponse(url="/admin", status_code=303)


@app.post("/ai-save")
def ai_save_recipe(
    title: str = Form(...),
    category: str = Form(...),
    description: str = Form(...),
    image_url: str = Form(""),
    ingredients: str = Form(...),
    instructions: str = Form(...),
    rating: float = Form(...),
    difficulty: str = Form(...),
    cost: str = Form(...),
    prep_time: str = Form(...),
    tags: str = Form(""),
    source_url: str = Form(""),
):
    db = get_db()

    recipe = Recipe(
        title=title,
        category=category,
        description=description,
        image_url=image_url,
        ingredients=ingredients,
        instructions=instructions,
        rating=rating,
        difficulty=difficulty,
        cost=cost,
        prep_time=prep_time,
        tags=tags,
        source="gemini",
        source_url=source_url,
        created_by="Gemini",
    )

    db.add(recipe)
    db.commit()
    db.refresh(recipe)

    recipe_id = recipe.id

    db.close()

    return JSONResponse(
        content={
            "success": True,
            "message": "המתכון נשמר בהצלחה",
            "recipe_id": recipe_id,
        }
    )