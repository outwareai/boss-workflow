"""
Web routes for staff onboarding and OAuth flows.
"""

import json
import logging
import secrets
from typing import Optional
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel, EmailStr

from config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Template directory
TEMPLATES_DIR = Path(__file__).parent / "templates"

# OAuth state storage (in production, use Redis)
oauth_states = {}


class OnboardingData(BaseModel):
    """Data submitted from onboarding form."""
    name: str
    email: str
    role: str
    discord_id: str
    discord_username: Optional[str] = None
    calendar_connected: bool = False
    tasks_connected: bool = False
    calendar_token: Optional[str] = None
    tasks_token: Optional[str] = None


# ============================================================================
# Web Pages
# ============================================================================

@router.get("/onboard", response_class=HTMLResponse)
async def onboard_page():
    """Serve the staff onboarding page."""
    template_path = TEMPLATES_DIR / "onboard.html"

    if not template_path.exists():
        raise HTTPException(status_code=404, detail="Onboarding page not found")

    return HTMLResponse(content=template_path.read_text(encoding="utf-8"))


@router.get("/onboard/success", response_class=HTMLResponse)
async def onboard_success():
    """Success page after onboarding."""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Welcome!</title>
        <style>
            body {
                font-family: 'Inter', sans-serif;
                background: #0a0a0a;
                color: #fff;
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
                margin: 0;
            }
            .container {
                text-align: center;
                padding: 40px;
            }
            .success-icon {
                width: 80px;
                height: 80px;
                background: #1a3d1a;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0 auto 24px;
                color: #4ade80;
                font-size: 40px;
            }
            h1 { color: #4ade80; margin-bottom: 16px; }
            p { color: #888; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="success-icon">✓</div>
            <h1>Welcome to the Team!</h1>
            <p>Your account has been set up successfully.</p>
            <p>You can close this window.</p>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/api/onboard")
async def submit_onboarding(data: OnboardingData):
    """
    Process onboarding form submission.

    Saves to Google Sheets and PostgreSQL database.
    """
    logger.info(f"Processing onboarding for {data.name} ({data.email})")

    try:
        # Import here to avoid circular imports
        from ..integrations.sheets import sheets_integration

        # Initialize sheets if needed
        if not await sheets_integration.initialize():
            raise HTTPException(status_code=500, detail="Failed to connect to Google Sheets")

        # Add/update team member in Google Sheets
        calendar_id = data.email  # Default calendar ID is email

        success = await sheets_integration.update_team_member(
            name=data.name,
            discord_id=data.discord_id,
            email=data.email,
            role=data.role,
            status="Active",
            calendar_id=calendar_id
        )

        if not success:
            raise HTTPException(status_code=500, detail="Failed to save to Google Sheets")

        # Also save to database if available
        try:
            from ..database.repositories import get_team_repository
            team_repo = get_team_repository()

            await team_repo.upsert({
                "name": data.name,
                "email": data.email,
                "discord_id": data.discord_id,
                "role": data.role,
                "status": "Active"
            })
            logger.info(f"Saved {data.name} to database")
        except Exception as db_error:
            logger.warning(f"Database save failed (non-critical): {db_error}")

        # Store OAuth tokens if provided
        if data.calendar_token:
            await store_oauth_token(data.email, "calendar", data.calendar_token)
        if data.tasks_token:
            await store_oauth_token(data.email, "tasks", data.tasks_token)

        logger.info(f"Successfully onboarded {data.name}")

        return {
            "success": True,
            "message": f"Welcome {data.name}! Your account has been set up.",
            "data": {
                "name": data.name,
                "email": data.email,
                "role": data.role
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Onboarding error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Google OAuth2 Flow
# ============================================================================

# IMPORTANT: callback route must come BEFORE the parameterized {service} route
@router.get("/auth/google/callback")
async def google_auth_callback(code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    """
    Handle Google OAuth2 callback.
    """
    if error:
        html = f"""
        <!DOCTYPE html>
        <html>
        <head><title>Authorization Failed</title></head>
        <body>
            <script>
                window.opener.postMessage({{ type: 'auth_error', message: '{error}' }}, '*');
                window.close();
            </script>
        </body>
        </html>
        """
        return HTMLResponse(content=html)

    if not state or state not in oauth_states:
        raise HTTPException(status_code=400, detail="Invalid state")

    state_data = oauth_states.pop(state)
    service = state_data["service"]

    try:
        import httpx

        client_id = settings.google_oauth_client_id
        client_secret = settings.google_oauth_client_secret
        redirect_uri = f"{settings.webhook_base_url}/auth/google/callback"

        # Exchange code for tokens
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri
                }
            )

            if response.status_code != 200:
                raise Exception(f"Token exchange failed: {response.text}")

            tokens = response.json()

            # Get user's email from userinfo endpoint
            access_token = tokens.get("access_token")
            user_email = None
            if access_token:
                userinfo_response = await client.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                if userinfo_response.status_code == 200:
                    userinfo = userinfo_response.json()
                    user_email = userinfo.get("email")

        # Store tokens in database
        if user_email and tokens.get("refresh_token"):
            try:
                from ..database.repositories import get_oauth_repository
                oauth_repo = get_oauth_repository()
                await oauth_repo.store_token(
                    email=user_email,
                    service=service,
                    refresh_token=tokens.get("refresh_token"),
                    access_token=tokens.get("access_token"),
                    expires_in=tokens.get("expires_in"),
                    scopes=tokens.get("scope"),
                )
                logger.info(f"Stored {service} OAuth token for {user_email}")
            except Exception as db_error:
                logger.warning(f"Failed to store OAuth token in DB: {db_error}")

        # Return success to popup
        html = f"""
        <!DOCTYPE html>
        <html>
        <head><title>Connected!</title>
        <style>
            body {{ font-family: sans-serif; background: #0a0a0a; color: #fff; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
            .success {{ text-align: center; }}
            .icon {{ color: #4ade80; font-size: 48px; margin-bottom: 16px; }}
        </style>
        </head>
        <body>
            <div class="success">
                <div class="icon">✓</div>
                <h2>Google {service.title()} Connected!</h2>
                <p style="color: #888;">{user_email or 'Your account'}</p>
                <p>You can close this window.</p>
            </div>
            <script>
                window.opener.postMessage({{
                    type: '{service}_connected',
                    token: '{tokens.get("refresh_token", "")}',
                    email: '{user_email or ""}'
                }}, '*');
                setTimeout(() => window.close(), 2000);
            </script>
        </body>
        </html>
        """
        return HTMLResponse(content=html)

    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        html = f"""
        <!DOCTYPE html>
        <html>
        <head><title>Error</title></head>
        <body>
            <script>
                window.opener.postMessage({{ type: '{service}_error', message: 'Authorization failed' }}, '*');
                window.close();
            </script>
        </body>
        </html>
        """
        return HTMLResponse(content=html)


@router.get("/auth/google/{service}")
async def google_auth_start(service: str, state: Optional[str] = None):
    """
    Start Google OAuth2 flow for calendar or tasks.
    """
    if service not in ["calendar", "tasks"]:
        raise HTTPException(status_code=400, detail="Invalid service")

    # Check if OAuth client ID is configured
    client_id = settings.google_oauth_client_id if hasattr(settings, 'google_oauth_client_id') else None

    if not client_id:
        # Return error page explaining setup needed
        html = f"""
        <!DOCTYPE html>
        <html>
        <head><title>Setup Required</title>
        <style>
            body {{ font-family: sans-serif; background: #0a0a0a; color: #fff; padding: 40px; }}
            .error {{ background: #3d1a1a; border: 1px solid #ef4444; padding: 20px; border-radius: 8px; max-width: 500px; margin: 0 auto; }}
            h2 {{ color: #ef4444; }}
            code {{ background: #2a2a2a; padding: 2px 6px; border-radius: 4px; }}
        </style>
        </head>
        <body>
            <div class="error">
                <h2>Google OAuth Not Configured</h2>
                <p>To enable Google {service} integration, add these environment variables:</p>
                <ul>
                    <li><code>GOOGLE_OAUTH_CLIENT_ID</code></li>
                    <li><code>GOOGLE_OAUTH_CLIENT_SECRET</code></li>
                </ul>
                <p>Get these from Google Cloud Console → APIs & Services → Credentials</p>
                <script>
                    setTimeout(() => {{
                        window.opener.postMessage({{ type: '{service}_error', message: 'OAuth not configured' }}, '*');
                        window.close();
                    }}, 3000);
                </script>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=html)

    # Generate state token
    state_token = secrets.token_urlsafe(32)
    oauth_states[state_token] = {
        "service": service,
        "form_state": state,
        "created": datetime.now().isoformat()
    }

    # Build OAuth URL - include email scope to identify user
    service_scopes = {
        "calendar": "https://www.googleapis.com/auth/calendar",
        "tasks": "https://www.googleapis.com/auth/tasks"
    }
    # Always include email scope to get user identity
    full_scope = f"{service_scopes[service]} email"

    redirect_uri = f"{settings.webhook_base_url}/auth/google/callback"

    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={client_id}&"
        f"redirect_uri={redirect_uri}&"
        "response_type=code&"
        f"scope={full_scope}&"
        f"state={state_token}&"
        "access_type=offline&"
        "prompt=consent"
    )

    return RedirectResponse(url=auth_url)


async def store_oauth_token(email: str, service: str, token: str):
    """Store OAuth refresh token for a user."""
    # For now, store in settings/notes
    # In production, encrypt and store in database
    logger.info(f"Storing {service} token for {email}")

    try:
        from ..integrations.sheets import sheets_integration

        # Add a note about the connection
        # The actual token should be stored securely (encrypted in database)
        # For now, we just mark that they've connected
        pass

    except Exception as e:
        logger.warning(f"Failed to store token: {e}")


# ============================================================================
# Team List (Admin View)
# ============================================================================

@router.get("/team", response_class=HTMLResponse)
async def team_list():
    """View current team members (admin only in future)."""
    try:
        from ..integrations.sheets import sheets_integration

        if not await sheets_integration.initialize():
            raise HTTPException(status_code=500, detail="Failed to connect")

        members = await sheets_integration.get_all_team_members()

        rows = ""
        for m in members:
            rows += f"""
            <tr>
                <td>{m.get('Name', '')}</td>
                <td>{m.get('Email', '')}</td>
                <td>{m.get('Role', '')}</td>
                <td>{m.get('Status', '')}</td>
                <td>{m.get('Discord ID', '')}</td>
            </tr>
            """

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Team Members</title>
            <style>
                body {{ font-family: 'Inter', sans-serif; background: #0a0a0a; color: #fff; padding: 40px; }}
                h1 {{ color: #4ade80; margin-bottom: 24px; }}
                table {{ width: 100%; border-collapse: collapse; background: #1a1a1a; border-radius: 8px; overflow: hidden; }}
                th {{ background: #252525; padding: 12px 16px; text-align: left; font-size: 12px; text-transform: uppercase; color: #888; }}
                td {{ padding: 12px 16px; border-top: 1px solid #333; }}
                tr:hover td {{ background: #252525; }}
                .btn {{ display: inline-block; background: #4ade80; color: #0a0a0a; padding: 10px 20px; border-radius: 8px; text-decoration: none; font-weight: 600; margin-bottom: 24px; }}
            </style>
        </head>
        <body>
            <a href="/onboard" class="btn">+ Add Team Member</a>
            <h1>Team Members</h1>
            <table>
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Email</th>
                        <th>Role</th>
                        <th>Status</th>
                        <th>Discord ID</th>
                    </tr>
                </thead>
                <tbody>
                    {rows if rows else '<tr><td colspan="5" style="text-align:center;color:#666;">No team members yet</td></tr>'}
                </tbody>
            </table>
        </body>
        </html>
        """
        return HTMLResponse(content=html)

    except Exception as e:
        logger.error(f"Error loading team: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Audit Dashboard (v2.0.5)
# ============================================================================

@router.get("/audit", response_class=HTMLResponse)
async def audit_dashboard():
    """
    Audit dashboard showing system activity and metrics.

    Includes:
    - Message queue status
    - Rate limiting stats
    - Recent task activity
    - Error logs
    """
    try:
        # Get message queue stats
        queue_stats = {}
        dead_letters = []
        try:
            from ..services.message_queue import get_message_queue
            queue = get_message_queue()
            queue_stats = queue.get_queue_stats()
            dead_letters = queue.get_dead_letter_messages()
        except Exception as e:
            queue_stats = {"error": str(e)}

        # Get rate limiter stats
        rate_stats = {}
        try:
            from ..services.rate_limiter import get_rate_limiter
            limiter = get_rate_limiter()
            rate_stats = limiter.get_stats()
        except Exception as e:
            rate_stats = {"error": str(e)}

        # Get recent tasks from database
        recent_tasks = []
        try:
            from ..database.repositories import get_task_repository
            repo = get_task_repository()
            # Get latest 10 tasks
            tasks = await repo.get_recent(limit=10)
            recent_tasks = [
                {
                    "task_id": t.task_id,
                    "title": t.title[:40] if t.title else "",
                    "status": t.status,
                    "assignee": t.assignee or "-",
                    "created": t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else "",
                }
                for t in tasks
            ]
        except Exception as e:
            logger.debug(f"Could not get recent tasks: {e}")

        # Build task rows
        task_rows = ""
        for t in recent_tasks:
            status_color = {
                "completed": "#4ade80",
                "in_progress": "#60a5fa",
                "pending": "#fbbf24",
                "blocked": "#f87171",
            }.get(t.get("status", ""), "#888")
            task_rows += f"""
                <tr>
                    <td><code>{t.get('task_id', '')}</code></td>
                    <td>{t.get('title', '')}</td>
                    <td style="color:{status_color}">{t.get('status', '')}</td>
                    <td>{t.get('assignee', '')}</td>
                    <td>{t.get('created', '')}</td>
                </tr>
            """

        # Build dead letter rows
        dead_rows = ""
        for dl in dead_letters[:10]:
            dead_rows += f"""
                <tr>
                    <td><code>{dl.get('id', '')}</code></td>
                    <td>{dl.get('type', '')}</td>
                    <td>{dl.get('retry_count', 0)}</td>
                    <td style="color:#f87171">{dl.get('last_error', '')[:50]}</td>
                    <td>{dl.get('created_at', '')}</td>
                </tr>
            """

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Audit Dashboard - Boss Workflow</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                * {{ box-sizing: border-box; margin: 0; padding: 0; }}
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0a0a0a; color: #fff; padding: 24px; }}
                h1 {{ margin-bottom: 24px; color: #4ade80; }}
                h2 {{ margin: 32px 0 16px; color: #60a5fa; font-size: 18px; }}
                .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 32px; }}
                .card {{ background: #1a1a1a; border-radius: 12px; padding: 20px; }}
                .card-title {{ font-size: 12px; text-transform: uppercase; color: #888; margin-bottom: 8px; }}
                .card-value {{ font-size: 28px; font-weight: 600; color: #4ade80; }}
                .card-value.warning {{ color: #fbbf24; }}
                .card-value.error {{ color: #f87171; }}
                table {{ width: 100%; border-collapse: collapse; background: #1a1a1a; border-radius: 12px; overflow: hidden; margin-bottom: 24px; }}
                th {{ background: #252525; padding: 12px 16px; text-align: left; font-size: 12px; text-transform: uppercase; color: #888; }}
                td {{ padding: 12px 16px; border-top: 1px solid #333; font-size: 14px; }}
                tr:hover td {{ background: #252525; }}
                code {{ background: #333; padding: 2px 6px; border-radius: 4px; font-size: 12px; }}
                .timestamp {{ font-size: 12px; color: #666; margin-top: 24px; }}
                .nav {{ margin-bottom: 24px; }}
                .nav a {{ color: #60a5fa; text-decoration: none; margin-right: 16px; }}
                .nav a:hover {{ text-decoration: underline; }}
            </style>
        </head>
        <body>
            <div class="nav">
                <a href="/">Home</a>
                <a href="/team">Team</a>
                <a href="/health">Health</a>
                <a href="/audit">Audit</a>
            </div>

            <h1>📊 Audit Dashboard</h1>

            <div class="grid">
                <div class="card">
                    <div class="card-title">Queued Messages</div>
                    <div class="card-value">{queue_stats.get('total_queued', 0)}</div>
                </div>
                <div class="card">
                    <div class="card-title">Dead Letters</div>
                    <div class="card-value {'error' if queue_stats.get('dead_letter', 0) > 0 else ''}">{queue_stats.get('dead_letter', 0)}</div>
                </div>
                <div class="card">
                    <div class="card-title">Worker Status</div>
                    <div class="card-value">{'Running' if queue_stats.get('worker_running') else 'Stopped'}</div>
                </div>
                <div class="card">
                    <div class="card-title">Rate Limited Keys</div>
                    <div class="card-value">{rate_stats.get('active_keys', 0)}</div>
                </div>
            </div>

            <h2>📋 Recent Tasks</h2>
            <table>
                <thead>
                    <tr>
                        <th>Task ID</th>
                        <th>Title</th>
                        <th>Status</th>
                        <th>Assignee</th>
                        <th>Created</th>
                    </tr>
                </thead>
                <tbody>
                    {task_rows if task_rows else '<tr><td colspan="5" style="text-align:center;color:#666;">No recent tasks</td></tr>'}
                </tbody>
            </table>

            <h2>⚠️ Dead Letter Queue</h2>
            <table>
                <thead>
                    <tr>
                        <th>Message ID</th>
                        <th>Type</th>
                        <th>Retries</th>
                        <th>Last Error</th>
                        <th>Created</th>
                    </tr>
                </thead>
                <tbody>
                    {dead_rows if dead_rows else '<tr><td colspan="5" style="text-align:center;color:#666;">No dead letters 🎉</td></tr>'}
                </tbody>
            </table>

            <p class="timestamp">Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </body>
        </html>
        """
        return HTMLResponse(content=html)

    except Exception as e:
        logger.error(f"Error loading audit dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/audit/stats", response_class=JSONResponse)
async def audit_stats_api():
    """API endpoint for audit statistics."""
    try:
        stats = {
            "timestamp": datetime.now().isoformat(),
            "message_queue": {},
            "rate_limiter": {},
        }

        try:
            from ..services.message_queue import get_message_queue
            queue = get_message_queue()
            stats["message_queue"] = queue.get_queue_stats()
        except Exception as e:
            stats["message_queue"] = {"error": str(e)}

        try:
            from ..services.rate_limiter import get_rate_limiter
            limiter = get_rate_limiter()
            stats["rate_limiter"] = limiter.get_stats()
        except Exception as e:
            stats["rate_limiter"] = {"error": str(e)}

        return stats

    except Exception as e:
        logger.error(f"Error getting audit stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
