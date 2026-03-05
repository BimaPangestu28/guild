use anyhow::Result;
use include_dir::{include_dir, Dir};
use tiny_http::{Header, Method, Response, Server};

use crate::db;
use std::fs;
use std::path::PathBuf;

static DASHBOARD_DIR: Dir = include_dir!("$CARGO_MANIFEST_DIR/dashboard/dist");

pub fn serve(port: u16, dashboard_dir: Option<PathBuf>) -> Result<()> {
    let server = Server::http(format!("0.0.0.0:{}", port))
        .map_err(|e| anyhow::anyhow!("Failed to start server: {}", e))?;

    println!("Guild dashboard: http://localhost:{}", port);

    for request in server.incoming_requests() {
        let url = request.url().to_string();
        let method = request.method().clone();

        let result = match (method, url.as_str()) {
            // API endpoints
            (Method::Get, "/api/status") => handle_status(request),
            (Method::Get, "/api/heroes") => handle_heroes(request),
            (Method::Get, "/api/quests") => handle_quests(request),
            (Method::Get, "/api/projects") => handle_projects(request),
            (Method::Get, "/api/log") => handle_log(request),
            (Method::Get, "/api/locks") => handle_locks(request),
            (Method::Get, "/api/mcps") => handle_mcps(request),

            // Static files (dashboard)
            (Method::Get, path) => {
                let path = path.to_string();
                serve_static(request, &path, &dashboard_dir)
            }

            _ => {
                let resp = Response::from_string("Not Found").with_status_code(404);
                request.respond(resp).map_err(|e| e.into())
            }
        };

        if let Err(e) = result {
            eprintln!("Error handling request: {}", e);
        }
    }
    Ok(())
}

fn cors_header() -> Header {
    Header::from_bytes("Access-Control-Allow-Origin", "*").unwrap()
}

fn json_content_type() -> Header {
    Header::from_bytes("Content-Type", "application/json").unwrap()
}

fn respond_json(
    request: tiny_http::Request,
    json: serde_json::Value,
) -> Result<()> {
    let body = serde_json::to_string(&json)?;
    let resp = Response::from_string(body)
        .with_header(cors_header())
        .with_header(json_content_type());
    request.respond(resp)?;
    Ok(())
}

fn respond_error(request: tiny_http::Request, status: u16, msg: &str) -> Result<()> {
    let body = serde_json::json!({ "error": msg });
    let resp = Response::from_string(serde_json::to_string(&body)?)
        .with_status_code(status)
        .with_header(cors_header())
        .with_header(json_content_type());
    request.respond(resp)?;
    Ok(())
}

// ---------- API Handlers ----------

fn handle_status(request: tiny_http::Request) -> Result<()> {
    let conn = match db::open() {
        Ok(c) => c,
        Err(e) => return respond_error(request, 500, &format!("DB error: {}", e)),
    };

    let hero_total: i64 = conn
        .query_row("SELECT COUNT(*) FROM heroes", [], |r| r.get(0))
        .unwrap_or(0);
    let hero_online: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM heroes WHERE status = 'online'",
            [],
            |r| r.get(0),
        )
        .unwrap_or(0);
    let hero_on_quest: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM heroes WHERE status = 'on_quest'",
            [],
            |r| r.get(0),
        )
        .unwrap_or(0);

    let quests_active: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM quests WHERE status = 'active'",
            [],
            |r| r.get(0),
        )
        .unwrap_or(0);
    let quests_backlog: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM quests WHERE status = 'backlog'",
            [],
            |r| r.get(0),
        )
        .unwrap_or(0);
    let quests_blocked: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM quests WHERE status = 'blocked'",
            [],
            |r| r.get(0),
        )
        .unwrap_or(0);
    let quests_done_today: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM quests WHERE status = 'done' AND completed_at >= date('now')",
            [],
            |r| r.get(0),
        )
        .unwrap_or(0);

    let projects_active: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM projects WHERE status = 'active'",
            [],
            |r| r.get(0),
        )
        .unwrap_or(0);

    let json = serde_json::json!({
        "heroes": {
            "total": hero_total,
            "online": hero_online,
            "on_quest": hero_on_quest,
        },
        "quests": {
            "active": quests_active,
            "backlog": quests_backlog,
            "blocked": quests_blocked,
            "done_today": quests_done_today,
        },
        "projects": {
            "active": projects_active,
        }
    });

    respond_json(request, json)
}

fn handle_heroes(request: tiny_http::Request) -> Result<()> {
    let conn = match db::open() {
        Ok(c) => c,
        Err(e) => return respond_error(request, 500, &format!("DB error: {}", e)),
    };

    let mut stmt = conn.prepare(
        "SELECT id, name, class, status, level, xp, current_quest_id FROM heroes ORDER BY name",
    )?;

    let heroes: Vec<serde_json::Value> = stmt
        .query_map([], |row| {
            let id: String = row.get(0)?;
            let name: String = row.get(1)?;
            let class: String = row.get(2)?;
            let status: String = row.get(3)?;
            let level: i64 = row.get(4)?;
            let xp: i64 = row.get(5)?;
            let current_quest_id: Option<String> = row.get(6)?;
            Ok((id, name, class, status, level, xp, current_quest_id))
        })?
        .filter_map(|r| r.ok())
        .map(|(id, name, class, status, level, xp, current_quest_id)| {
            // Fetch skills for this hero
            let skills = fetch_hero_skills(&conn, &id);
            serde_json::json!({
                "id": id,
                "name": name,
                "class": class,
                "status": status,
                "level": level,
                "xp": xp,
                "current_quest_id": current_quest_id,
                "skills": skills,
            })
        })
        .collect();

    respond_json(request, serde_json::json!(heroes))
}

fn fetch_hero_skills(conn: &rusqlite::Connection, hero_id: &str) -> Vec<serde_json::Value> {
    let mut stmt = match conn.prepare(
        "SELECT name, proficiency FROM hero_skills WHERE hero_id = ?1 ORDER BY name",
    ) {
        Ok(s) => s,
        Err(_) => return vec![],
    };

    stmt.query_map([hero_id], |row| {
        let name: String = row.get(0)?;
        let proficiency: i64 = row.get(1)?;
        Ok(serde_json::json!({
            "name": name,
            "proficiency": proficiency,
        }))
    })
    .map(|rows| rows.filter_map(|r| r.ok()).collect())
    .unwrap_or_default()
}

fn handle_quests(request: tiny_http::Request) -> Result<()> {
    let conn = match db::open() {
        Ok(c) => c,
        Err(e) => return respond_error(request, 500, &format!("DB error: {}", e)),
    };

    let mut stmt = conn.prepare(
        "SELECT q.id, q.title, q.tier, q.type, q.status, q.project_id, q.branch, q.assigned_to, \
         COALESCE(h.name, '') \
         FROM quests q \
         LEFT JOIN heroes h ON q.assigned_to = h.id \
         ORDER BY q.created_at DESC",
    )?;

    let quests: Vec<serde_json::Value> = stmt
        .query_map([], |row| {
            Ok(serde_json::json!({
                "id": row.get::<_, String>(0)?,
                "title": row.get::<_, String>(1)?,
                "tier": row.get::<_, String>(2)?,
                "type": row.get::<_, String>(3)?,
                "status": row.get::<_, String>(4)?,
                "project_id": row.get::<_, String>(5)?,
                "branch": row.get::<_, String>(6)?,
                "assigned_to": row.get::<_, Option<String>>(7)?,
                "hero_name": row.get::<_, String>(8)?,
            }))
        })?
        .filter_map(|r| r.ok())
        .collect();

    respond_json(request, serde_json::json!(quests))
}

fn handle_projects(request: tiny_http::Request) -> Result<()> {
    let conn = match db::open() {
        Ok(c) => c,
        Err(e) => return respond_error(request, 500, &format!("DB error: {}", e)),
    };

    let mut stmt = conn.prepare(
        "SELECT id, name, display_name, language, status, path FROM projects ORDER BY name",
    )?;

    let projects: Vec<serde_json::Value> = stmt
        .query_map([], |row| {
            Ok(serde_json::json!({
                "id": row.get::<_, String>(0)?,
                "name": row.get::<_, String>(1)?,
                "display_name": row.get::<_, String>(2)?,
                "language": row.get::<_, Option<String>>(3)?,
                "status": row.get::<_, String>(4)?,
                "path": row.get::<_, String>(5)?,
            }))
        })?
        .filter_map(|r| r.ok())
        .collect();

    respond_json(request, serde_json::json!(projects))
}

fn handle_log(request: tiny_http::Request) -> Result<()> {
    let conn = match db::open() {
        Ok(c) => c,
        Err(e) => return respond_error(request, 500, &format!("DB error: {}", e)),
    };

    let mut stmt = conn.prepare(
        "SELECT timestamp, actor, action, quest_id, level \
         FROM activity_log ORDER BY timestamp DESC LIMIT 50",
    )?;

    let entries: Vec<serde_json::Value> = stmt
        .query_map([], |row| {
            Ok(serde_json::json!({
                "timestamp": row.get::<_, String>(0)?,
                "actor": row.get::<_, String>(1)?,
                "action": row.get::<_, String>(2)?,
                "quest_id": row.get::<_, Option<String>>(3)?,
                "level": row.get::<_, String>(4)?,
            }))
        })?
        .filter_map(|r| r.ok())
        .collect();

    respond_json(request, serde_json::json!(entries))
}

fn handle_locks(request: tiny_http::Request) -> Result<()> {
    let conn = match db::open() {
        Ok(c) => c,
        Err(e) => return respond_error(request, 500, &format!("DB error: {}", e)),
    };

    let locks = db::get_locks(&conn)?;

    let json: Vec<serde_json::Value> = locks
        .into_iter()
        .map(|(file_path, quest_id, hero_name, locked_at)| {
            serde_json::json!({
                "file_path": file_path,
                "quest_id": quest_id,
                "hero_name": hero_name,
                "locked_at": locked_at,
            })
        })
        .collect();

    respond_json(request, serde_json::json!(json))
}

fn handle_mcps(request: tiny_http::Request) -> Result<()> {
    let conn = match db::open() {
        Ok(c) => c,
        Err(e) => return respond_error(request, 500, &format!("DB error: {}", e)),
    };

    let mut stmt = conn.prepare(
        "SELECT name, display_name, url, command, skills_served, status FROM mcp_servers ORDER BY name",
    )?;

    let mcps: Vec<serde_json::Value> = stmt
        .query_map([], |row| {
            let url: Option<String> = row.get(2)?;
            let command: Option<String> = row.get(3)?;
            let mcp_type = if url.is_some() {
                "http"
            } else if command.is_some() {
                "stdio"
            } else {
                "unknown"
            };
            let skills_str: String = row.get(4)?;
            let skills: serde_json::Value =
                serde_json::from_str(&skills_str).unwrap_or(serde_json::json!([]));

            Ok(serde_json::json!({
                "name": row.get::<_, String>(0)?,
                "display_name": row.get::<_, String>(1)?,
                "type": mcp_type,
                "skills_served": skills,
                "status": row.get::<_, String>(5)?,
            }))
        })?
        .filter_map(|r| r.ok())
        .collect();

    respond_json(request, serde_json::json!(mcps))
}

// ---------- Static File Serving ----------

fn serve_static(
    request: tiny_http::Request,
    path: &str,
    dashboard_dir: &Option<PathBuf>,
) -> Result<()> {
    // Prevent path traversal
    let clean = path.trim_start_matches('/');
    if clean.contains("..") {
        let resp = Response::from_string("Forbidden").with_status_code(403);
        request.respond(resp)?;
        return Ok(());
    }

    let relative = if clean.is_empty() { "index.html" } else { clean };

    // If dashboard_dir is Some and exists on disk, serve from disk (dev mode)
    if let Some(dir) = dashboard_dir {
        if dir.is_dir() {
            let file_path = dir.join(relative);
            let (actual_path, content) = if file_path.is_file() {
                let data = fs::read(&file_path)?;
                (file_path, data)
            } else {
                // SPA fallback
                let index = dir.join("index.html");
                if index.is_file() {
                    let data = fs::read(&index)?;
                    (index, data)
                } else {
                    let resp = Response::from_string("Not Found").with_status_code(404);
                    request.respond(resp)?;
                    return Ok(());
                }
            };

            let content_type = guess_content_type(&actual_path);
            let header = Header::from_bytes("Content-Type", content_type).unwrap();
            let resp = Response::from_data(content).with_header(header);
            request.respond(resp)?;
            return Ok(());
        }
    }

    // Serve from embedded DASHBOARD_DIR
    let content = if let Some(file) = DASHBOARD_DIR.get_file(relative) {
        file.contents().to_vec()
    } else {
        // SPA fallback: serve embedded index.html
        match DASHBOARD_DIR.get_file("index.html") {
            Some(index) => index.contents().to_vec(),
            None => {
                let resp = Response::from_string("Dashboard not found").with_status_code(404);
                request.respond(resp)?;
                return Ok(());
            }
        }
    };

    let content_type = guess_content_type_str(relative);
    let header = Header::from_bytes("Content-Type", content_type).unwrap();
    let resp = Response::from_data(content).with_header(header);
    request.respond(resp)?;
    Ok(())
}

fn guess_content_type(path: &PathBuf) -> &'static str {
    match path.extension().and_then(|e| e.to_str()) {
        Some("html") => "text/html; charset=utf-8",
        Some("js") => "application/javascript; charset=utf-8",
        Some("css") => "text/css; charset=utf-8",
        Some("json") => "application/json; charset=utf-8",
        Some("png") => "image/png",
        Some("svg") => "image/svg+xml",
        Some("jpg") | Some("jpeg") => "image/jpeg",
        Some("ico") => "image/x-icon",
        Some("woff") => "font/woff",
        Some("woff2") => "font/woff2",
        Some("ttf") => "font/ttf",
        _ => "application/octet-stream",
    }
}

fn guess_content_type_str(path: &str) -> &'static str {
    if let Some(dot_pos) = path.rfind('.') {
        match &path[dot_pos + 1..] {
            "html" => "text/html; charset=utf-8",
            "js" => "application/javascript; charset=utf-8",
            "css" => "text/css; charset=utf-8",
            "json" => "application/json; charset=utf-8",
            "png" => "image/png",
            "svg" => "image/svg+xml",
            "jpg" | "jpeg" => "image/jpeg",
            "ico" => "image/x-icon",
            "woff" => "font/woff",
            "woff2" => "font/woff2",
            "ttf" => "font/ttf",
            _ => "application/octet-stream",
        }
    } else {
        "application/octet-stream"
    }
}
