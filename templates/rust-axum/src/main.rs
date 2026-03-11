use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::Json,
    routing::{delete, get, post, put},
    Router,
};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::PgPool;
use std::env;

#[derive(Serialize, sqlx::FromRow)]
struct Item {
    id: i32,
    name: String,
    description: Option<String>,
    created_at: DateTime<Utc>,
}

#[derive(Deserialize)]
struct ItemBody {
    name: String,
    description: Option<String>,
}

async fn health() -> Json<serde_json::Value> {
    Json(serde_json::json!({"status": "ok"}))
}

async fn list_items(State(pool): State<PgPool>) -> Result<Json<Vec<Item>>, StatusCode> {
    let items = sqlx::query_as::<_, Item>("SELECT id, name, description, created_at FROM items ORDER BY id")
        .fetch_all(&pool)
        .await
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    Ok(Json(items))
}

async fn create_item(
    State(pool): State<PgPool>,
    Json(body): Json<ItemBody>,
) -> Result<(StatusCode, Json<Item>), StatusCode> {
    if body.name.is_empty() {
        return Err(StatusCode::BAD_REQUEST);
    }
    let item = sqlx::query_as::<_, Item>(
        "INSERT INTO items (name, description) VALUES ($1, $2) RETURNING id, name, description, created_at",
    )
    .bind(&body.name)
    .bind(&body.description)
    .fetch_one(&pool)
    .await
    .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    Ok((StatusCode::CREATED, Json(item)))
}

async fn get_item(
    State(pool): State<PgPool>,
    Path(id): Path<i32>,
) -> Result<Json<Item>, StatusCode> {
    let item = sqlx::query_as::<_, Item>(
        "SELECT id, name, description, created_at FROM items WHERE id = $1",
    )
    .bind(id)
    .fetch_optional(&pool)
    .await
    .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?
    .ok_or(StatusCode::NOT_FOUND)?;
    Ok(Json(item))
}

async fn update_item(
    State(pool): State<PgPool>,
    Path(id): Path<i32>,
    Json(body): Json<ItemBody>,
) -> Result<Json<Item>, StatusCode> {
    let item = sqlx::query_as::<_, Item>(
        "UPDATE items SET name = $1, description = $2 WHERE id = $3 RETURNING id, name, description, created_at",
    )
    .bind(&body.name)
    .bind(&body.description)
    .bind(id)
    .fetch_optional(&pool)
    .await
    .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?
    .ok_or(StatusCode::NOT_FOUND)?;
    Ok(Json(item))
}

async fn delete_item(
    State(pool): State<PgPool>,
    Path(id): Path<i32>,
) -> Result<StatusCode, StatusCode> {
    let result = sqlx::query("DELETE FROM items WHERE id = $1")
        .bind(id)
        .execute(&pool)
        .await
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    if result.rows_affected() == 0 {
        return Err(StatusCode::NOT_FOUND);
    }
    Ok(StatusCode::NO_CONTENT)
}

#[tokio::main]
async fn main() {
    let database_url = env::var("DATABASE_URL").expect("DATABASE_URL must be set");
    let pool = PgPool::connect(&database_url).await.expect("Failed to connect to database");

    sqlx::query(
        "CREATE TABLE IF NOT EXISTS items (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )",
    )
    .execute(&pool)
    .await
    .expect("Failed to create items table");

    let app = Router::new()
        .route("/health", get(health))
        .route("/items", get(list_items).post(create_item))
        .route("/items/:id", get(get_item).put(update_item).delete(delete_item))
        .with_state(pool);

    let listener = tokio::net::TcpListener::bind("0.0.0.0:8080").await.unwrap();
    println!("Server running on port 8080");
    axum::serve(listener, app).await.unwrap();
}
