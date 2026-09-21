-- SPDX-License-Identifier: MIT
CREATE SCHEMA IF NOT EXISTS meal;
CREATE TABLE IF NOT EXISTS meal.recipe (
    recipe_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    base_servings INTEGER NOT NULL CHECK (base_servings BETWEEN 1 AND 100),
    ingredients_json TEXT NOT NULL,
    steps_json TEXT NOT NULL,
    video_url TEXT,
    notes TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_meal_recipe_user ON meal.recipe(user_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS meal.shopping_plan (
    user_id TEXT PRIMARY KEY,
    items_json TEXT NOT NULL,
    checked_json TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
