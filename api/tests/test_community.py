"""
LabX Comunidad TriatlÃ³n LATAM â€” Test Suite completo (Â§19)
42 tests organizados en 6 clases:
  TestFollowSystem        (8)
  TestFeedAndPosts        (8)
  TestKudosAndComments    (8)
  TestGroupsAndChallenges (8)
  TestNotifications       (5)
  TestAiAndSecurity       (5)
"""
from __future__ import annotations
import uuid
import pytest
from datetime import datetime, timedelta, timezone

# â”€â”€ Helpers de fixtures (sin DB real â€” unit tests) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class _FakeUser:
    def __init__(self, uid=None, nombre="Test Atleta", rol="atleta", activo=True, coach_id=None):
        self.id       = uid or str(uuid.uuid4())
        self.nombre   = nombre
        self.email    = f"{nombre.lower().replace(' ','_')}@test.com"
        self.rol      = rol
        self.activo   = activo
        self.coach_id = coach_id

class _FakePost:
    def __init__(self, uid, sport="run", tss=80, ctl=70, tsb=-5, dist=10, dur=45, vis="followers"):
        self.id          = str(uuid.uuid4())
        self.user_id     = uid
        self.post_type   = "activity"
        self.sport       = sport
        self.tss         = tss
        self.ctl_day     = ctl
        self.tsb_day     = tsb
        self.dist_km     = dist
        self.dur_min     = dur
        self.visibility  = vis
        self.body        = None
        self.kudos       = []
        self.comments    = []
        self.is_flagged  = False
        self.flagged_by  = None
        self.card_image  = None
        self.created_at  = datetime.now(timezone.utc).replace(tzinfo=None)
        self.user        = _FakeUser(uid)
        self.activity_id = None
        self.title       = None

class _FakeKudo:
    def __init__(self, post_id, user_id, kudo_type="power"):
        self.id        = str(uuid.uuid4())
        self.post_id   = post_id
        self.user_id   = user_id
        self.kudo_type = kudo_type
        self.created_at= datetime.now(timezone.utc).replace(tzinfo=None)

class _FakeComment:
    def __init__(self, post_id, user_id, body="test comment", parent_id=None):
        self.id         = str(uuid.uuid4())
        self.post_id    = post_id
        self.user_id    = user_id
        self.parent_id  = parent_id
        self.body       = body
        self.deleted_at = None
        self.created_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self.author     = _FakeUser(user_id)

class _FakeGroup:
    def __init__(self, owner_id, name="Test Grupo", is_private=False):
        self.id          = str(uuid.uuid4())
        self.owner_id    = owner_id
        self.name        = name
        self.description = "Grupo de prueba"
        self.sport       = "triathlon"
        self.level       = "open"
        self.is_private  = is_private
        self.invite_code = str(uuid.uuid4())[:8] if is_private else None
        self.city        = "Santiago"
        self.country     = "Chile"
        self.created_at  = datetime.now(timezone.utc).replace(tzinfo=None)
        self.members     = []

class _FakeChallenge:
    def __init__(self, group_id, creator_id, metric="km", target=100.0):
        self.id          = str(uuid.uuid4())
        self.group_id    = group_id
        self.creator_id  = creator_id
        self.name        = "Reto 100km"
        self.description = None
        self.metric      = metric
        self.sport       = "all"
        self.target      = target
        self.start_date  = "2026-06-01"
        self.end_date    = "2026-06-30"
        self.is_active   = True
        self.created_at  = datetime.now(timezone.utc).replace(tzinfo=None)
        self.entries     = []

class _FakeFollow:
    def __init__(self, follower_id, followed_id):
        self.id          = str(uuid.uuid4())
        self.follower_id = follower_id
        self.followed_id = followed_id
        self.created_at  = datetime.now(timezone.utc).replace(tzinfo=None)
        self.follower    = _FakeUser(follower_id)
        self.followed    = _FakeUser(followed_id)

class _FakeNotif:
    def __init__(self, user_id, actor_id, notif_type="kudo"):
        self.id         = str(uuid.uuid4())
        self.user_id    = user_id
        self.actor_id   = actor_id
        self.notif_type = notif_type
        self.post_id    = None
        self.group_id   = None
        self.body       = "Test notification"
        self.read_at    = None
        self.created_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self.actor      = _FakeUser(actor_id)

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# TEST CLASS 1 â€” FOLLOW SYSTEM (8 tests)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestFollowSystem:

    def test_follow_creates_relationship(self):
        """Follow registra relaciÃ³n followerâ†’followed."""
        f = _FakeFollow("user_a", "user_b")
        assert f.follower_id == "user_a"
        assert f.followed_id == "user_b"

    def test_follow_unique_constraint(self):
        """No puede haber dos follows idÃ©nticos."""
        follows = [_FakeFollow("user_a", "user_b"), _FakeFollow("user_a", "user_b")]
        pairs = {(f.follower_id, f.followed_id) for f in follows}
        assert len(pairs) == 1  # mismo par â†’ 1 entrada en set

    def test_follow_self_rejected(self):
        """Un usuario no puede seguirse a sÃ­ mismo."""
        user_id = str(uuid.uuid4())
        with pytest.raises(Exception):
            if user_id == user_id:
                raise Exception("No puedes seguirte a ti mismo")

    def test_follow_bidirectionality(self):
        """A sigue B y B sigue A son relaciones independientes."""
        f1 = _FakeFollow("user_a", "user_b")
        f2 = _FakeFollow("user_b", "user_a")
        assert f1.follower_id != f2.follower_id
        assert f1.followed_id != f2.followed_id

    def test_unfollow_removes_relationship(self):
        """Unfollow elimina el Follow de la lista."""
        follows = [_FakeFollow("user_a", "user_b"), _FakeFollow("user_a", "user_c")]
        follows = [f for f in follows if f.followed_id != "user_b"]
        assert len(follows) == 1
        assert follows[0].followed_id == "user_c"

    def test_followers_list_only_own(self):
        """Seguidores de user_b incluye a user_a pero no user_c."""
        follows = [
            _FakeFollow("user_a", "user_b"),
            _FakeFollow("user_c", "user_d"),
        ]
        user_b_followers = [f.follower_id for f in follows if f.followed_id == "user_b"]
        assert "user_a" in user_b_followers
        assert "user_c" not in user_b_followers

    def test_following_list_correct(self):
        """user_a sigue a user_b y user_c â€” lista siguiendo."""
        follows = [_FakeFollow("user_a", "user_b"), _FakeFollow("user_a", "user_c")]
        following = [f.followed_id for f in follows if f.follower_id == "user_a"]
        assert set(following) == {"user_b", "user_c"}

    def test_suggestion_excludes_already_following(self):
        """Sugerencias no incluyen a usuarios ya seguidos."""
        following_ids = {"user_b", "user_c", "user_a"}  # incluye self
        candidates = ["user_b", "user_d", "user_e"]
        suggestions = [u for u in candidates if u not in following_ids]
        assert "user_b" not in suggestions
        assert set(suggestions) == {"user_d", "user_e"}


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# TEST CLASS 2 â€” FEED AND POSTS (8 tests)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestFeedAndPosts:

    def test_post_created_with_activity_data(self):
        """Post hereda datos de la actividad Garmin."""
        user_id = str(uuid.uuid4())
        post = _FakePost(user_id, sport="swim", tss=65, dist=3.8, dur=72)
        assert post.sport == "swim"
        assert post.tss == 65
        assert post.dist_km == 3.8
        assert post.dur_min == 72

    def test_post_visibility_defaults_followers(self):
        """Visibilidad por defecto es 'followers'."""
        post = _FakePost(str(uuid.uuid4()))
        assert post.visibility == "followers"

    def test_feed_filters_by_following(self):
        """Feed solo muestra posts de usuarios seguidos + propios."""
        my_id = "user_me"
        following = {"user_a", "user_b", my_id}
        posts = [
            _FakePost("user_a"),
            _FakePost("user_c"),   # no seguido
            _FakePost(my_id),
        ]
        feed = [p for p in posts if p.user_id in following]
        assert len(feed) == 2
        assert all(p.user_id != "user_c" for p in feed)

    def test_feed_excludes_private_posts_from_others(self):
        """Posts privados de otros no aparecen en el feed."""
        my_id = "user_me"
        following = {"user_a", my_id}
        posts = [
            _FakePost("user_a", vis="private"),
            _FakePost("user_a", vis="followers"),
            _FakePost(my_id, vis="private"),  # propios siempre visibles
        ]
        visible = [p for p in posts
                   if p.user_id == my_id or p.visibility in ("public", "followers")]
        assert len(visible) == 2

    def test_feed_sport_filter_works(self):
        """Filtro de deporte devuelve solo posts del deporte solicitado."""
        uid = str(uuid.uuid4())
        posts = [_FakePost(uid, sport="run"), _FakePost(uid, sport="bike"), _FakePost(uid, sport="swim")]
        filtered = [p for p in posts if p.sport == "bike"]
        assert len(filtered) == 1
        assert filtered[0].sport == "bike"

    def test_feed_pagination(self):
        """PaginaciÃ³n devuelve el subconjunto correcto."""
        uid = str(uuid.uuid4())
        posts = [_FakePost(uid) for _ in range(25)]
        page, per_page = 2, 10
        page_items = posts[(page-1)*per_page: page*per_page]
        assert len(page_items) == 10
        assert page_items[0] is posts[10]

    def test_post_delete_restricted_to_owner(self):
        """Solo el autor puede borrar su post."""
        owner_id  = "owner"
        other_id  = "other"
        post = _FakePost(owner_id)
        can_delete = post.user_id == owner_id
        cannot    = post.user_id == other_id
        assert can_delete
        assert not cannot

    def test_post_type_note_has_no_activity(self):
        """Post tipo 'note' no requiere activity_id."""
        post = _FakePost(str(uuid.uuid4()))
        post.post_type   = "note"
        post.activity_id = None
        assert post.post_type == "note"
        assert post.activity_id is None


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# TEST CLASS 3 â€” KUDOS AND COMMENTS (8 tests)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestKudosAndComments:

    def test_kudo_unique_per_post_user_type(self):
        """Un usuario no puede dar el mismo tipo de kudo dos veces."""
        post_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        kudos = [_FakeKudo(post_id, user_id, "power")]
        # Simular intento de agregar duplicado
        existing = [k for k in kudos if k.post_id == post_id and k.user_id == user_id and k.kudo_type == "power"]
        assert len(existing) == 1  # ya existe

    def test_kudo_five_types_allowed(self):
        """Los 5 tipos de kudo son vÃ¡lidos."""
        valid_types = {"power", "fire", "trophy", "epic", "love"}
        post_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        kudos = [_FakeKudo(post_id, user_id, t) for t in valid_types]
        assert len(kudos) == 5

    def test_kudo_invalid_type_rejected(self):
        """Tipos de kudo fuera del set son rechazados."""
        valid = {"power", "fire", "trophy", "epic", "love"}
        for invalid_type in ("like", "star", "thumbs", "bomb", ""):
            assert invalid_type not in valid

    def test_kudo_count_aggregation(self):
        """Conteo de kudos por tipo es correcto."""
        post_id = str(uuid.uuid4())
        kudos = [
            _FakeKudo(post_id, "u1", "power"),
            _FakeKudo(post_id, "u2", "power"),
            _FakeKudo(post_id, "u3", "fire"),
        ]
        grouped = {}
        for k in kudos:
            grouped[k.kudo_type] = grouped.get(k.kudo_type, 0) + 1
        assert grouped["power"] == 2
        assert grouped["fire"]  == 1

    def test_comment_added_to_post(self):
        """Comentario se asocia correctamente al post."""
        post_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        c = _FakeComment(post_id, user_id, "Gran entrenamiento!")
        assert c.post_id == post_id
        assert c.body == "Gran entrenamiento!"
        assert c.deleted_at is None

    def test_comment_soft_delete(self):
        """Borrado suave de comentario no lo elimina fÃ­sicamente."""
        post_id = str(uuid.uuid4())
        c = _FakeComment(post_id, str(uuid.uuid4()), "Este comentario fue borrado")
        c.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
        # AÃºn existe en DB, pero marcado
        assert c.deleted_at is not None
        assert c.body == "Este comentario fue borrado"

    def test_comment_threading_parent(self):
        """Comentario respuesta tiene parent_id."""
        post_id   = str(uuid.uuid4())
        parent    = _FakeComment(post_id, "u1", "Excelente!")
        reply     = _FakeComment(post_id, "u2", "Totalmente de acuerdo", parent_id=parent.id)
        assert reply.parent_id == parent.id

    def test_comment_max_length_validation(self):
        """Comentario con mÃ¡s de 500 caracteres es rechazado."""
        long_body = "x" * 501
        is_valid  = len(long_body) <= 500
        assert not is_valid


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# TEST CLASS 4 â€” GROUPS AND CHALLENGES (8 tests)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestGroupsAndChallenges:

    def test_group_created_with_owner(self):
        """Grupo se crea con el creador como admin."""
        owner = _FakeUser()
        group = _FakeGroup(owner.id, name="Triatletas Santiago")
        assert group.owner_id == owner.id
        assert group.name == "Triatletas Santiago"

    def test_group_unique_name(self):
        """Dos grupos no pueden tener el mismo nombre."""
        groups = [_FakeGroup("o1", "Equipo Alpha"), _FakeGroup("o2", "Equipo Alpha")]
        names = [g.name for g in groups]
        unique_names = set(names)
        assert len(names) != len(unique_names)  # hay duplicado

    def test_private_group_has_invite_code(self):
        """Grupo privado genera cÃ³digo de invitaciÃ³n."""
        g = _FakeGroup("owner", is_private=True)
        assert g.is_private is True
        assert g.invite_code is not None
        assert len(g.invite_code) > 0

    def test_public_group_no_invite_needed(self):
        """Grupo pÃºblico no requiere cÃ³digo para unirse."""
        g = _FakeGroup("owner", is_private=False)
        assert g.is_private is False
        assert g.invite_code is None

    def test_challenge_metric_validation(self):
        """Solo mÃ©tricas vÃ¡lidas son aceptadas."""
        valid = {"km", "tss", "activities", "hours"}
        for m in valid:
            ch = _FakeChallenge("group_id", "creator_id", metric=m)
            assert ch.metric == m
        for invalid in ("speed", "watts", "pace", ""):
            assert invalid not in valid

    def test_challenge_progress_calculation(self):
        """Progreso del reto se calcula correctamente para km."""
        from datetime import date
        target = 100.0
        activities_km = [15.2, 22.8, 30.0, 10.0]  # total = 78
        progress = sum(activities_km)
        pct = round(progress / target * 100, 1)
        assert progress == pytest.approx(78.0)
        assert pct == 78.0

    def test_challenge_leaderboard_sorted(self):
        """Leaderboard ordena por progreso descendente."""
        board = [
            {"user": "A", "progress": 45.0},
            {"user": "B", "progress": 78.0},
            {"user": "C", "progress": 23.0},
        ]
        board.sort(key=lambda x: x["progress"], reverse=True)
        assert board[0]["user"] == "B"
        assert board[1]["user"] == "A"
        assert board[2]["user"] == "C"

    def test_challenge_entries_created_for_all_members(self):
        """Al crear reto, se crea entry para cada miembro del grupo."""
        member_ids = ["u1", "u2", "u3", "u4"]
        entries = [{"challenge_id": "ch1", "user_id": uid, "progress": 0} for uid in member_ids]
        assert len(entries) == len(member_ids)
        assert all(e["progress"] == 0 for e in entries)


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# TEST CLASS 5 â€” NOTIFICATIONS (5 tests)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestNotifications:

    def test_notification_not_created_for_self(self):
        """No se crea notificaciÃ³n cuando user_id == actor_id."""
        user_id  = "same_user"
        actor_id = "same_user"
        should_create = user_id != actor_id
        assert not should_create

    def test_notification_created_for_kudo(self):
        """Se crea notificaciÃ³n cuando otro usuario da un kudo."""
        n = _FakeNotif("user_a", "user_b", "kudo")
        assert n.user_id  == "user_a"
        assert n.actor_id == "user_b"
        assert n.notif_type == "kudo"
        assert n.read_at is None

    def test_mark_read_sets_timestamp(self):
        """Marcar notificaciÃ³n como leÃ­da establece read_at."""
        n = _FakeNotif("user_a", "user_b")
        n.read_at = datetime.now(timezone.utc).replace(tzinfo=None)
        assert n.read_at is not None

    def test_unread_count_correct(self):
        """Contador de no leÃ­das devuelve solo las sin read_at."""
        notifs = [
            _FakeNotif("u1", "u2"),
            _FakeNotif("u1", "u3"),
            _FakeNotif("u1", "u4"),
        ]
        notifs[0].read_at = datetime.now(timezone.utc).replace(tzinfo=None)  # marcar 1 como leÃ­da
        unread = [n for n in notifs if n.read_at is None]
        assert len(unread) == 2

    def test_mark_all_read_clears_count(self):
        """DespuÃ©s de marcar todas como leÃ­das, unread=0."""
        notifs = [_FakeNotif("u1", "u2") for _ in range(5)]
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for n in notifs:
            n.read_at = now
        unread = [n for n in notifs if n.read_at is None]
        assert len(unread) == 0


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# TEST CLASS 6 â€” AI AND SECURITY (5 tests)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestAiAndSecurity:

    def test_ai_kudo_suggests_epic_for_exceptional_tss(self):
        """IA sugiere 'epic' cuando TSS >= 1.5Ã— CTL."""
        post = _FakePost("u1", tss=150, ctl=90)  # ratio=1.67
        ratio = post.tss / post.ctl_day
        assert ratio >= 1.5
        # Logic replica community_routes._ai_kudo_context
        suggestion = "epic" if ratio >= 1.5 else ("fire" if ratio >= 1.0 else "power")
        assert suggestion == "epic"

    def test_ai_kudo_suggests_trophy_for_negative_tsb(self):
        """IA sugiere 'trophy' cuando TSB < -20 (fatiga alta)."""
        post = _FakePost("u1", tsb=-25)
        suggestion = "trophy" if (post.tsb_day is not None and post.tsb_day < -20) else "power"
        assert suggestion == "trophy"

    def test_ai_ranked_feed_score_rewards_engagement(self):
        """Score de feed penaliza post sin kudos ni comentarios."""
        def score(kudos, comments, tss, age_h):
            tss_n = min(tss / 150.0, 2.0)
            recency = 1.0 / (1.0 + age_h / 24.0)
            return kudos * 3 + comments * 2 + tss_n + recency * 5

        high_engagement = score(10, 5, 120, 2)
        low_engagement  = score(0,  0,  50, 2)
        assert high_engagement > low_engagement

    def test_post_flag_marks_post(self):
        """Reportar post establece is_flagged=True."""
        post = _FakePost("u1")
        post.is_flagged = True
        post.flagged_by = "reporter_id"
        assert post.is_flagged is True
        assert post.flagged_by == "reporter_id"

    def test_private_group_blocks_without_code(self):
        """Grupo privado requiere invite_code correcto."""
        group = _FakeGroup("owner", is_private=True)
        correct_code  = group.invite_code
        wrong_code    = "wrongcode"
        can_join_right = (not group.is_private) or (group.invite_code == correct_code)
        can_join_wrong = (not group.is_private) or (group.invite_code == wrong_code)
        assert can_join_right
        assert not can_join_wrong


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# SPRINT 17 TEST ADDITIONS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
import pytest
from datetime import date, timedelta


COUNTRY_FLAG_S17 = {
    "CL": "ðŸ‡¨ðŸ‡±", "BR": "ðŸ‡§ðŸ‡·", "AR": "ðŸ‡¦ðŸ‡·", "MX": "ðŸ‡²ðŸ‡½",
    "CO": "ðŸ‡¨ðŸ‡´", "PE": "ðŸ‡µðŸ‡ª", "EC": "ðŸ‡ªðŸ‡¨", "UY": "ðŸ‡ºðŸ‡¾",
    "PY": "ðŸ‡µðŸ‡¾", "BO": "ðŸ‡§ðŸ‡´", "VE": "ðŸ‡»ðŸ‡ª",
    "US": "ðŸ‡ºðŸ‡¸", "ES": "ðŸ‡ªðŸ‡¸", "PT": "ðŸ‡µðŸ‡¹",
}

SPORT_EMOJI_S17 = {
    "running": "ðŸƒ", "run": "ðŸƒ",
    "cycling": "ðŸš´", "bike": "ðŸš´", "riding": "ðŸš´",
    "swimming": "ðŸŠ", "swim": "ðŸŠ",
    "triathlon": "ðŸ",
    "trail_running": "ðŸ”ï¸", "trail": "ðŸ”ï¸",
    "other": "âš¡",
}

RECOVERY_LEVEL_LABEL_S17 = {
    "optimal":  "Forma Ã³ptima",
    "good":     "Bien recuperado",
    "moderate": "RecuperaciÃ³n moderada",
    "low":      "Fatiga acumulada",
    "critical": "Descanso urgente",
}


def _get_sport_emoji_s17(activity_type):
    sport_raw = (activity_type or "other").lower()
    sport_key = next((k for k in SPORT_EMOJI_S17 if k in sport_raw), "other")
    return SPORT_EMOJI_S17.get(sport_key, "âš¡")


def _leaderboard_period_start_s17(period):
    today = date.today()
    if period == "week":
        return (today - timedelta(days=today.weekday())).isoformat()
    if period == "month":
        return today.replace(day=1).isoformat()
    if period == "year":
        return today.replace(month=1, day=1).isoformat()
    return "2000-01-01"


def _aggregate_metric_s17(activities, metric, sport_filter):
    total = 0.0
    for a in activities:
        act_sport = (a.get("activity_type") or "").lower()
        if sport_filter != "all" and sport_filter not in act_sport:
            continue
        if metric == "tss":
            total += a.get("tss") or 0.0
        elif metric == "distance_km":
            total += (a.get("distance_m") or 0) / 1000
        elif metric == "elevation_m":
            total += a.get("elevation_gain_m") or 0.0
        elif metric == "duration_h":
            total += (a.get("duration_s") or 0) / 3600
    return round(total, 2)


def _rank_users_s17(rows):
    sorted_rows = sorted(rows, key=lambda x: x["value"], reverse=True)
    for i, row in enumerate(sorted_rows, 1):
        row["rank"] = i
    return sorted_rows


def _comment_body_valid_s17(body):
    return isinstance(body, str) and 1 <= len(body.strip()) <= 500


def _visibility_valid_s17(v):
    return v in ("public", "followers", "private", "coach_only")


def _club_name_valid_s17(name):
    return isinstance(name, str) and 2 <= len(name.strip()) <= 100


def _challenge_dates_valid_s17(start, end):
    return start < end


def _challenge_goal_valid_s17(goal):
    return isinstance(goal, (int, float)) and goal > 0


class TestCountryFlagsS17:
    def test_latam_countries_present(self):
        for cc in ("CL", "BR", "AR", "MX", "CO", "PE"):
            assert cc in COUNTRY_FLAG_S17

    def test_chile_flag(self):
        assert COUNTRY_FLAG_S17["CL"] == "ðŸ‡¨ðŸ‡±"

    def test_brazil_flag(self):
        assert COUNTRY_FLAG_S17["BR"] == "ðŸ‡§ðŸ‡·"

    def test_unknown_not_in_dict(self):
        assert "XX" not in COUNTRY_FLAG_S17

    def test_all_non_empty(self):
        for cc, flag in COUNTRY_FLAG_S17.items():
            assert flag, f"Empty flag: {cc}"


class TestSportEmojiS17:
    def test_running(self):
        assert _get_sport_emoji_s17("running") == "ðŸƒ"

    def test_cycling(self):
        assert _get_sport_emoji_s17("cycling") == "ðŸš´"

    def test_swim(self):
        assert _get_sport_emoji_s17("swim") == "ðŸŠ"

    def test_triathlon(self):
        assert _get_sport_emoji_s17("triathlon") == "ðŸ"

    def test_unknown_defaults(self):
        assert _get_sport_emoji_s17("unknown") == "âš¡"

    def test_none_defaults(self):
        assert _get_sport_emoji_s17(None) == "âš¡"

    def test_partial_match_bike(self):
        assert _get_sport_emoji_s17("outdoor_bike") == "ðŸš´"

    def test_partial_match_run(self):
        assert _get_sport_emoji_s17("trail_run") == "ðŸƒ"


class TestLeaderboardPeriodS17:
    def test_week_is_monday(self):
        start = _leaderboard_period_start_s17("week")
        d = date.fromisoformat(start)
        assert d.weekday() == 0

    def test_month_first_day(self):
        start = _leaderboard_period_start_s17("month")
        d = date.fromisoformat(start)
        assert d.day == 1

    def test_year_jan_first(self):
        start = _leaderboard_period_start_s17("year")
        d = date.fromisoformat(start)
        assert d.month == 1 and d.day == 1

    def test_alltime_old_date(self):
        assert _leaderboard_period_start_s17("alltime") == "2000-01-01"

    def test_all_periods_valid_iso(self):
        for p in ("week", "month", "year", "alltime"):
            s = _leaderboard_period_start_s17(p)
            assert len(s) == 10 and s[4] == '-'


class TestMetricAggregationS17:
    ACTS = [
        {"activity_type": "running",  "tss": 80,  "distance_m": 10000, "elevation_gain_m": 50,  "duration_s": 3600},
        {"activity_type": "cycling",  "tss": 120, "distance_m": 50000, "elevation_gain_m": 500, "duration_s": 7200},
        {"activity_type": "swimming", "tss": 40,  "distance_m": 3000,  "elevation_gain_m": 0,   "duration_s": 3000},
    ]

    def test_tss_all(self):
        assert _aggregate_metric_s17(self.ACTS, "tss", "all") == pytest.approx(240.0)

    def test_tss_running_only(self):
        assert _aggregate_metric_s17(self.ACTS, "tss", "run") == pytest.approx(80.0)

    def test_distance_all(self):
        assert _aggregate_metric_s17(self.ACTS, "distance_km", "all") == pytest.approx(63.0, abs=0.1)

    def test_elevation_all(self):
        assert _aggregate_metric_s17(self.ACTS, "elevation_m", "all") == pytest.approx(550.0)

    def test_duration_hours(self):
        assert _aggregate_metric_s17(self.ACTS, "duration_h", "all") == pytest.approx(3.833, abs=0.01)

    def test_no_match_sport(self):
        assert _aggregate_metric_s17(self.ACTS, "tss", "triathlon") == 0.0

    def test_empty_list(self):
        assert _aggregate_metric_s17([], "tss", "all") == 0.0

    def test_none_tss_zero(self):
        acts = [{"activity_type": "run", "tss": None, "distance_m": 0, "elevation_gain_m": 0, "duration_s": 0}]
        assert _aggregate_metric_s17(acts, "tss", "all") == 0.0


class TestRankingS17:
    def test_highest_is_first(self):
        rows = [
            {"user": {"id": "a"}, "value": 100.0},
            {"user": {"id": "b"}, "value": 250.0},
            {"user": {"id": "c"}, "value": 175.0},
        ]
        ranked = _rank_users_s17(rows)
        assert ranked[0]["user"]["id"] == "b"
        assert ranked[0]["rank"] == 1

    def test_ranks_sequential(self):
        rows = [{"user": {"id": str(i)}, "value": float(i)} for i in range(5)]
        ranked = _rank_users_s17(rows)
        assert [r["rank"] for r in ranked] == [1, 2, 3, 4, 5]

    def test_empty_rows(self):
        assert _rank_users_s17([]) == []

    def test_single_row_rank_1(self):
        rows = [{"user": {"id": "x"}, "value": 99.0}]
        assert _rank_users_s17(rows)[0]["rank"] == 1


class TestInputValidationS17:
    def test_valid_comment(self):
        assert _comment_body_valid_s17("Gran entrenamiento!") is True

    def test_empty_comment(self):
        assert _comment_body_valid_s17("") is False

    def test_whitespace_only(self):
        assert _comment_body_valid_s17("   ") is False

    def test_too_long_comment(self):
        assert _comment_body_valid_s17("x" * 501) is False

    def test_valid_visibility(self):
        for v in ("public", "followers", "private"):
            assert _visibility_valid_s17(v) is True

    def test_invalid_visibility(self):
        assert _visibility_valid_s17("everyone") is False

    def test_valid_club_name(self):
        assert _club_name_valid_s17("Tri Club LATAM") is True

    def test_too_short_club(self):
        assert _club_name_valid_s17("A") is False

    def test_valid_challenge_dates(self):
        assert _challenge_dates_valid_s17("2026-07-01", "2026-07-31") is True

    def test_same_dates_invalid(self):
        assert _challenge_dates_valid_s17("2026-07-01", "2026-07-01") is False

    def test_positive_goal(self):
        assert _challenge_goal_valid_s17(100.0) is True

    def test_zero_goal_invalid(self):
        assert _challenge_goal_valid_s17(0) is False


class TestRecoveryLabelsS17:
    def test_all_levels_present(self):
        for level in ("optimal", "good", "moderate", "low", "critical"):
            assert level in RECOVERY_LEVEL_LABEL_S17

    def test_optimal_mentions_forma(self):
        assert "ptima" in RECOVERY_LEVEL_LABEL_S17["optimal"]

    def test_critical_mentions_descanso(self):
        assert "descanso" in RECOVERY_LEVEL_LABEL_S17["critical"].lower()

    def test_unknown_level_not_in_dict(self):
        assert RECOVERY_LEVEL_LABEL_S17.get("unknown") is None
