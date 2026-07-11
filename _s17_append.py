
# =============================================================================
# SPRINT 17 — ENRICHED ACTIVITY FEED + LATAM LEADERBOARD + SEARCH + STATS
# =============================================================================

SPORT_EMOJI_S17 = {
    "running": "🏃", "run": "🏃",
    "cycling": "🚴", "bike": "🚴", "riding": "🚴",
    "swimming": "🏊", "swim": "🏊",
    "triathlon": "🏁",
    "trail_running": "🏔️", "trail": "🏔️",
    "strength": "💪", "workout": "💪",
    "other": "⚡",
}

COUNTRY_FLAG = {
    "CL": "🇨🇱", "BR": "🇧🇷", "AR": "🇦🇷", "MX": "🇲🇽",
    "CO": "🇨🇴", "PE": "🇵🇪", "EC": "🇪🇨", "UY": "🇺🇾",
    "PY": "🇵🇾", "BO": "🇧🇴", "VE": "🇻🇪",
    "US": "🇺🇸", "ES": "🇪🇸", "PT": "🇵🇹",
}

RECOVERY_LEVEL_LABEL = {
    "optimal":  "Forma óptima",
    "good":     "Bien recuperado",
    "moderate": "Recuperación moderada",
    "low":      "Fatiga acumulada",
    "critical": "Descanso urgente",
}


def _build_activity_card_s17(act, viewer_id, db):
    owner    = db.query(User).filter_by(id=act.user_id).first()
    act_date = str(act.start_time)[:10] if act.start_time else None

    rec = None
    if act_date:
        rec = db.query(RecoveryScore).filter_by(
            user_id=act.user_id, date_iso=act_date
        ).first()

    tl = None
    if act_date:
        tl = (
            db.query(GarminTrainingLoad)
            .filter_by(user_id=act.user_id, date_iso=act_date)
            .first()
        )

    sport_raw = (act.activity_type or "other").lower()
    sport_key = next((k for k in SPORT_EMOJI_S17 if k in sport_raw), "other")
    country   = getattr(owner, "country_code", None) if owner else None

    return {
        "id":          act.id,
        "type":        "garmin_activity",
        "user": {
            "id":             owner.id if owner else None,
            "name":           (owner.full_name or owner.email.split("@")[0]) if owner else "—",
            "avatar_initial": ((owner.full_name or owner.email)[0]).upper() if owner else "?",
            "country_code":   country,
            "country_flag":   COUNTRY_FLAG.get(country or "", ""),
        },
        "sport":        sport_raw,
        "sport_emoji":  SPORT_EMOJI_S17.get(sport_key, "⚡"),
        "name":         act.name or sport_raw.capitalize(),
        "date_iso":     act_date,
        "distance_km":  round((act.distance_m or 0) / 1000, 2),
        "duration_min": round((act.duration_s or 0) / 60, 1),
        "elevation_m":  act.elevation_gain_m,
        "tss":          round(act.tss, 1) if act.tss else None,
        "avg_hr":       act.avg_hr,
        "avg_pace_min_km": act.avg_pace_min_km,
        "avg_power_w":  act.avg_power_w,
        "recovery": {
            "score":      rec.score if rec else None,
            "level":      rec.level if rec else None,
            "color":      rec.color if rec else None,
            "label":      RECOVERY_LEVEL_LABEL.get(rec.level, "") if rec else None,
            "suggestion": rec.training_suggestion if rec else None,
        },
        "training_load": {
            "ctl": round(tl.ctl, 1) if tl and tl.ctl else None,
            "tsb": round(tl.tsb, 1) if tl and tl.tsb else None,
            "atl": round(tl.atl, 1) if tl and tl.atl else None,
        },
        "is_viewer_activity": act.user_id == viewer_id,
    }


@router.get("/activity-feed")
def garmin_activity_feed(
    limit: int = Query(20, le=50),
    offset: int = Query(0, ge=0),
    sport: Optional[str] = None,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    followed_ids = [
        f.followed_id for f in
        db.query(Follow).filter_by(follower_id=me.id).all()
    ]
    feed_ids = [me.id] + followed_ids

    q = db.query(GarminActivity).filter(
        GarminActivity.user_id.in_(feed_ids),
        GarminActivity.start_time.isnot(None),
    )
    if sport:
        q = q.filter(GarminActivity.activity_type.ilike(f"%{sport}%"))

    acts = (
        q.order_by(GarminActivity.start_time.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    cards = [_build_activity_card_s17(a, me.id, db) for a in acts]
    return {
        "feed":            cards,
        "count":           len(cards),
        "following_count": len(followed_ids),
        "has_more":        len(acts) == limit,
    }


@router.get("/leaderboard")
def latam_leaderboard(
    metric:       str           = Query("tss"),
    sport:        str           = Query("all"),
    period:       str           = Query("week"),
    country_code: Optional[str] = None,
    scope:        str           = Query("social"),
    limit:        int           = Query(25, le=50),
    db:    Session = Depends(get_db),
    me:    User    = Depends(get_current_user),
):
    from datetime import date as _date
    today = _date.today()
    if period == "week":
        start = today - timedelta(days=today.weekday())
    elif period == "month":
        start = today.replace(day=1)
    elif period == "year":
        start = today.replace(month=1, day=1)
    else:
        start = None
    start_iso = start.isoformat() if start else "2000-01-01"

    if scope == "social":
        followed_ids = [
            f.followed_id for f in
            db.query(Follow).filter_by(follower_id=me.id).all()
        ]
        user_ids = [me.id] + followed_ids
        users = db.query(User).filter(User.id.in_(user_ids)).all()
    elif scope == "country":
        cc = (country_code or getattr(me, "country_code", None) or "").upper()
        if not cc:
            raise HTTPException(400, "country_code required for country scope")
        users = db.query(User).filter(User.country_code == cc).all()
    else:
        users = db.query(User).limit(500).all()

    rows = []
    for u in users:
        acts_q = db.query(GarminActivity).filter(
            GarminActivity.user_id == u.id,
            GarminActivity.start_time >= f"{start_iso}T00:00:00",
        )
        if sport != "all":
            acts_q = acts_q.filter(
                GarminActivity.activity_type.ilike(f"%{sport}%")
            )
        acts = acts_q.all()
        total = 0.0
        for a in acts:
            if metric == "tss":
                total += a.tss or 0.0
            elif metric == "distance_km":
                total += (a.distance_m or 0) / 1000
            elif metric == "elevation_m":
                total += a.elevation_gain_m or 0.0
            elif metric == "duration_h":
                total += (a.duration_s or 0) / 3600
        country = getattr(u, "country_code", None)
        rows.append({
            "user": {
                "id":             u.id,
                "name":           (u.full_name or u.email.split("@")[0]),
                "avatar_initial": ((u.full_name or u.email)[0]).upper(),
                "country_code":   country,
                "country_flag":   COUNTRY_FLAG.get(country or "", ""),
            },
            "value":          round(total, 2),
            "is_me":          u.id == me.id,
            "activity_count": len(acts),
        })

    rows.sort(key=lambda x: x["value"], reverse=True)
    rows = rows[:limit]
    for i, r in enumerate(rows, 1):
        r["rank"] = i

    metric_labels = {
        "tss":         "TSS Total",
        "distance_km": "Km Totales",
        "elevation_m": "Elevación (m)",
        "duration_h":  "Horas de entrenamiento",
    }
    return {
        "leaderboard":    rows,
        "scope":          scope,
        "sport":          sport,
        "metric":         metric,
        "metric_label":   metric_labels.get(metric, metric),
        "period":         period,
        "period_start":   start_iso,
        "my_rank":        next((r["rank"] for r in rows if r["is_me"]), None),
        "total_athletes": len(rows),
    }


@router.get("/search")
def search_athletes_s17(
    q:     str = Query(..., min_length=2, max_length=80),
    limit: int = Query(10, le=25),
    db:    Session = Depends(get_db),
    me:    User    = Depends(get_current_user),
):
    term = f"%{q.strip()}%"
    candidates = db.query(User).filter(
        (User.full_name.ilike(term)) | (User.email.ilike(term))
    ).limit(limit + 1).all()

    following_ids = {
        f.followed_id for f in
        db.query(Follow).filter_by(follower_id=me.id).all()
    }
    results = []
    for u in candidates:
        if u.id == me.id:
            continue
        country = getattr(u, "country_code", None)
        tl = (
            db.query(GarminTrainingLoad)
            .filter_by(user_id=u.id)
            .order_by(GarminTrainingLoad.date_iso.desc())
            .first()
        )
        results.append({
            "id":             u.id,
            "name":           u.full_name or u.email.split("@")[0],
            "avatar_initial": ((u.full_name or u.email)[0]).upper(),
            "country_code":   country,
            "country_flag":   COUNTRY_FLAG.get(country or "", ""),
            "is_following":   u.id in following_ids,
            "ctl":            round(tl.ctl, 1) if tl and tl.ctl else None,
        })
        if len(results) >= limit:
            break
    return {"results": results, "count": len(results), "query": q}


@router.get("/stats")
def my_community_stats(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    follower_count  = db.query(Follow).filter_by(followed_id=me.id).count()
    following_count = db.query(Follow).filter_by(follower_id=me.id).count()
    my_posts        = db.query(CommunityPost).filter_by(author_id=me.id).all()
    post_ids        = [p.id for p in my_posts]
    kudos_received  = (
        db.query(Kudo).filter(Kudo.post_id.in_(post_ids)).count()
        if post_ids else 0
    )
    clubs_count = db.query(GroupMember).filter_by(user_id=me.id).count()
    return {
        "follower_count":  follower_count,
        "following_count": following_count,
        "kudos_received":  kudos_received,
        "clubs_count":     clubs_count,
        "posts_count":     len(my_posts),
    }
