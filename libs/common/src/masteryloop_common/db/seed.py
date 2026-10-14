import hashlib
import logging
import uuid
from typing import Any

from masteryloop_common.db.base import SessionLocal
from masteryloop_common.db.dag import assert_graph_is_acyclic, validate_dag_edge
from masteryloop_common.db.models import (
    Class,
    Enrollment,
    Item,
    ItemOrigin,
    ItemParamHistory,
    ItemState,
    Learner,
    Mastery,
    Skill,
    SkillEdge,
    User,
    UserRole,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("masteryloop_seed")

SEED_NAMESPACE = uuid.UUID("e3f2a1b0-9c8d-4e5f-b6a7-0123456789ab")


def deterministic_uuid(name: str) -> uuid.UUID:
    """Produces a deterministic UUIDv5 for reproducible, idempotent seeding."""
    return uuid.uuid5(SEED_NAMESPACE, name)


def hash_password(password: str) -> str:
    """Deterministic hash for seeding purposes."""
    salt = "masteryloop_seed_salt"
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def seed_database(session: Session) -> None:
    """Populates the database with realistic initial entities idempotently."""
    logger.info("Initiating idempotent database seed...")

    # -------------------------------------------------------------------------
    # 1. Users (All 5 UserRoles represented)
    # -------------------------------------------------------------------------
    roles_seed = [
        ("admin.demo@masteryloop.ai", UserRole.admin),
        ("psychometrician.demo@masteryloop.ai", UserRole.psychometrician),
        ("author.demo@masteryloop.ai", UserRole.author),
        ("educator.demo@masteryloop.ai", UserRole.educator),
        ("learner.demo@masteryloop.ai", UserRole.learner),
    ]

    users_map: dict[str, User] = {}
    for email, role in roles_seed:
        user_id = deterministic_uuid(f"user:{email}")
        existing = session.scalar(select(User).where(User.email == email))
        if not existing:
            user = User(
                id=user_id,
                email=email,
                password_hash=hash_password("MasteryLoop2026!"),
                role=role,
            )
            session.add(user)
            users_map[email] = user
            logger.info("Seeded user: %s [%s]", email, role.value)
        else:
            users_map[email] = existing

    session.flush()

    # -------------------------------------------------------------------------
    # 2. 10-Skill Mathematics Prerequisite DAG
    # -------------------------------------------------------------------------
    skills_def = [
        (
            "ARITH-INT",
            "Integer Arithmetic & Operations",
            "Mathematics",
            "Addition, subtraction, multiplication, and division of positive and negative integers.",
        ),
        (
            "FRAC-BASIC",
            "Fraction Fundamentals",
            "Mathematics",
            "Visualizing proper, improper, and mixed fractions and identifying common denominators.",
        ),
        (
            "FRAC-ADD-SUB",
            "Fraction Addition & Subtraction",
            "Mathematics",
            "Adding and subtracting rational fractions with like and unlike denominators.",
        ),
        (
            "FRAC-MUL",
            "Fraction Multiplication",
            "Mathematics",
            "Cross-cancelling and multiplying numerators and denominators.",
        ),
        (
            "FRAC-DIV",
            "Fraction Division",
            "Mathematics",
            "Inverting divisors and reciprocal multiplication of rational numbers.",
        ),
        (
            "ALG-EXPR",
            "Algebraic Expressions",
            "Mathematics",
            "Evaluating, expanding, and simplifying algebraic variable expressions.",
        ),
        (
            "ALG-LIN-1VAR",
            "Single-Variable Linear Equations",
            "Mathematics",
            "Isolating unknown variables across multi-step linear equations.",
        ),
        (
            "ALG-LIN-SYS",
            "Systems of Linear Equations",
            "Mathematics",
            "Solving 2-variable systems via substitution, elimination, and graphing.",
        ),
        (
            "ALG-POLY",
            "Polynomial Operations & Factoring",
            "Mathematics",
            "Expanding binomials and factoring quadratic trinomials into linear factors.",
        ),
        (
            "ALG-QUAD",
            "Quadratic Equations & Roots",
            "Mathematics",
            "Solving quadratic equations via factoring, square roots, and the quadratic formula.",
        ),
    ]

    skills_map: dict[str, Skill] = {}
    for code, name, subject, desc in skills_def:
        s_id = deterministic_uuid(f"skill:{code}")
        existing = session.scalar(select(Skill).where(Skill.code == code))
        if not existing:
            s_obj = Skill(
                id=s_id,
                code=code,
                name=name,
                subject=subject,
                description=desc,
            )
            session.add(s_obj)
            skills_map[code] = s_obj
        else:
            skills_map[code] = existing

    session.flush()

    # 10-skill prerequisite graph relationships
    prerequisite_pairs = [
        ("ARITH-INT", "FRAC-BASIC"),
        ("FRAC-BASIC", "FRAC-ADD-SUB"),
        ("FRAC-ADD-SUB", "FRAC-MUL"),
        ("FRAC-MUL", "FRAC-DIV"),
        ("ARITH-INT", "ALG-EXPR"),
        ("FRAC-DIV", "ALG-LIN-1VAR"),
        ("ALG-EXPR", "ALG-LIN-1VAR"),
        ("ALG-LIN-1VAR", "ALG-LIN-SYS"),
        ("ALG-LIN-1VAR", "ALG-POLY"),
        ("ALG-POLY", "ALG-QUAD"),
    ]

    # Validate acyclicity incrementally using validate_dag_edge
    validated_edges: list[tuple[uuid.UUID, uuid.UUID]] = []
    for p_code, d_code in prerequisite_pairs:
        p_id = skills_map[p_code].id
        d_id = skills_map[d_code].id
        # Incremental validation
        validate_dag_edge(validated_edges, p_id, d_id)
        validated_edges.append((p_id, d_id))

    # Holistic graph validation assertion
    assert_graph_is_acyclic(validated_edges)

    for p_id, d_id in validated_edges:
        existing_edge = session.scalar(
            select(SkillEdge).where(
                SkillEdge.prereq_id == p_id,
                SkillEdge.skill_id == d_id,
            )
        )
        if not existing_edge:
            session.add(SkillEdge(prereq_id=p_id, skill_id=d_id))

    session.flush()
    logger.info("Validated and seeded acyclic 10-skill prerequisite DAG.")

    # -------------------------------------------------------------------------
    # 3. Classes, Learners (15), and Enrollments
    # -------------------------------------------------------------------------
    educator_user = users_map["educator.demo@masteryloop.ai"]

    c1_id = deterministic_uuid("class:grade9_algebra")
    c2_id = deterministic_uuid("class:grade10_precalc")

    c1 = session.scalar(select(Class).where(Class.id == c1_id))
    if not c1:
        c1 = Class(
            id=c1_id, name="Grade 9 Algebra Foundations", educator_id=educator_user.id
        )
        session.add(c1)

    c2 = session.scalar(select(Class).where(Class.id == c2_id))
    if not c2:
        c2 = Class(
            id=c2_id,
            name="Grade 10 Accelerated Mathematics",
            educator_id=educator_user.id,
        )
        session.add(c2)

    session.flush()

    # 15 Learners (Minors-safe data minimization)
    learner_names = [
        ("Maya Lin", "2026-Fall-A", c1_id),
        ("Ethan Vance", "2026-Fall-A", c1_id),
        ("Sophia Patel", "2026-Fall-A", c1_id),
        ("Liam O'Connor", "2026-Fall-A", c1_id),
        ("Amara Jackson", "2026-Fall-A", c1_id),
        ("Noah Tanaka", "2026-Fall-A", c1_id),
        ("Emma Rossi", "2026-Fall-A", c1_id),
        ("Lucas Kim", "2026-Fall-A", c1_id),
        ("Aria Washington", "2026-Fall-B", c2_id),
        ("Benjamin Scott", "2026-Fall-B", c2_id),
        ("Chloe Zhang", "2026-Fall-B", c2_id),
        ("Daniel Miller", "2026-Fall-B", c2_id),
        ("Elena Gomez", "2026-Fall-B", c2_id),
        ("Finn Gallagher", "2026-Fall-B", c2_id),
        ("Grace Adebayo", "2026-Fall-B", c2_id),
    ]

    learner_objects: list[Learner] = []
    for name, cohort, target_class_id in learner_names:
        l_id = deterministic_uuid(f"learner:{name}")
        existing_l = session.scalar(select(Learner).where(Learner.id == l_id))
        if not existing_l:
            l_obj = Learner(id=l_id, display_name=name, cohort=cohort)
            session.add(l_obj)
            session.flush()
            learner_objects.append(l_obj)
        else:
            learner_objects.append(existing_l)

        # Enrollment
        existing_enr = session.scalar(
            select(Enrollment).where(
                Enrollment.class_id == target_class_id,
                Enrollment.learner_id == l_id,
            )
        )
        if not existing_enr:
            session.add(Enrollment(class_id=target_class_id, learner_id=l_id))

    session.flush()
    logger.info("Seeded 2 classes and 15 enrolled learners.")

    # -------------------------------------------------------------------------
    # 4. Assessment Items (30 Items: 20 Active, 5 Pilot, 5 In-Review/Draft)
    # -------------------------------------------------------------------------
    items_spec: list[dict[str, Any]] = [
        # --- 20 Active Items (with calibrated 2PL IRT a and b) ---
        {
            "tag": "item_active_01",
            "stem": "Compute the sum: $-15 + (-27)$.",
            "options": {"A": "-42", "B": "-12", "C": "12", "D": "42"},
            "key": "A",
            "rationale": "Adding two negative integers preserves the negative sign: -15 + -27 = -42.",
            "skills": ["ARITH-INT"],
            "state": ItemState.active,
            "origin": ItemOrigin.human,
            "a": 1.15,
            "b": -1.85,
        },
        {
            "tag": "item_active_02",
            "stem": "Simplify: $(-8) \\times (-6) \\div (-4)$.",
            "options": {"A": "-12", "B": "12", "C": "-16", "D": "16"},
            "key": "A",
            "rationale": "(-8)*(-6) = 48. Then 48 / (-4) = -12.",
            "skills": ["ARITH-INT"],
            "state": ItemState.active,
            "origin": ItemOrigin.human,
            "a": 1.30,
            "b": -1.20,
        },
        {
            "tag": "item_active_03",
            "stem": "Which fraction is equivalent to $\\frac{18}{24}$ in simplest form?",
            "options": {"A": "3/4", "B": "2/3", "C": "9/12", "D": "6/8"},
            "key": "A",
            "rationale": "Dividing numerator and denominator by GCD(18, 24) = 6 yields 3/4.",
            "skills": ["FRAC-BASIC"],
            "state": ItemState.active,
            "origin": ItemOrigin.human,
            "a": 0.95,
            "b": -1.50,
        },
        {
            "tag": "item_active_04",
            "stem": "Convert $\\frac{29}{6}$ to a mixed number.",
            "options": {"A": "4 5/6", "B": "4 1/6", "C": "5 1/6", "D": "3 5/6"},
            "key": "A",
            "rationale": "29 divided by 6 is 4 with a remainder of 5, giving 4 5/6.",
            "skills": ["FRAC-BASIC"],
            "state": ItemState.active,
            "origin": ItemOrigin.human,
            "a": 1.05,
            "b": -1.10,
        },
        {
            "tag": "item_active_05",
            "stem": "Evaluate: $\\frac{3}{8} + \\frac{5}{12}$.",
            "options": {"A": "19/24", "B": "8/20", "C": "2/3", "D": "11/24"},
            "key": "A",
            "rationale": "LCM(8, 12) = 24. 9/24 + 10/24 = 19/24.",
            "skills": ["FRAC-ADD-SUB", "FRAC-BASIC"],
            "state": ItemState.active,
            "origin": ItemOrigin.human,
            "a": 1.40,
            "b": -0.65,
        },
        {
            "tag": "item_active_06",
            "stem": "Compute: $2\\frac{1}{3} - 1\\frac{3}{4}$.",
            "options": {"A": "7/12", "B": "5/12", "C": "1 1/12", "D": "2/7"},
            "key": "A",
            "rationale": "Convert to improper fractions: 7/3 - 7/4 = 28/12 - 21/12 = 7/12.",
            "skills": ["FRAC-ADD-SUB"],
            "state": ItemState.active,
            "origin": ItemOrigin.human,
            "a": 1.55,
            "b": -0.30,
        },
        {
            "tag": "item_active_07",
            "stem": "Multiply: $\\frac{4}{9} \\times \\frac{15}{16}$.",
            "options": {"A": "5/12", "B": "60/144", "C": "5/9", "D": "1/3"},
            "key": "A",
            "rationale": "Cross-cancelling: (4/16)*(15/9) = (1/4)*(5/3) = 5/12.",
            "skills": ["FRAC-MUL"],
            "state": ItemState.active,
            "origin": ItemOrigin.human,
            "a": 1.35,
            "b": -0.45,
        },
        {
            "tag": "item_active_08",
            "stem": "What is the result of dividing $\\frac{5}{7}$ by $\\frac{15}{28}$?",
            "options": {"A": "4/3", "B": "3/4", "C": "75/196", "D": "5/14"},
            "key": "A",
            "rationale": "Multiply by reciprocal: 5/7 * 28/15 = (5/15) * (28/7) = 1/3 * 4 = 4/3.",
            "skills": ["FRAC-DIV", "FRAC-MUL"],
            "state": ItemState.active,
            "origin": ItemOrigin.human,
            "a": 1.60,
            "b": -0.10,
        },
        {
            "tag": "item_active_09",
            "stem": "Evaluate the expression $3x^2 - 4y$ when $x = -2$ and $y = 3$.",
            "options": {"A": "0", "B": "24", "C": "-24", "D": "-12"},
            "key": "A",
            "rationale": "3*(-2)^2 - 4*(3) = 3*(4) - 12 = 12 - 12 = 0.",
            "skills": ["ALG-EXPR", "ARITH-INT"],
            "state": ItemState.active,
            "origin": ItemOrigin.human,
            "a": 1.25,
            "b": -0.40,
        },
        {
            "tag": "item_active_10",
            "stem": "Simplify the algebraic expression: $4(2x - 3) - 3(x + 5)$.",
            "options": {"A": "5x - 27", "B": "5x - 3", "C": "5x + 3", "D": "8x - 27"},
            "key": "A",
            "rationale": "8x - 12 - 3x - 15 = 5x - 27.",
            "skills": ["ALG-EXPR"],
            "state": ItemState.active,
            "origin": ItemOrigin.human,
            "a": 1.45,
            "b": -0.15,
        },
        {
            "tag": "item_active_11",
            "stem": "Solve for $x$: $5x - 7 = 3x + 11$.",
            "options": {"A": "9", "B": "2", "C": "4", "D": "18"},
            "key": "A",
            "rationale": "Subtract 3x: 2x - 7 = 11. Add 7: 2x = 18. Divide by 2: x = 9.",
            "skills": ["ALG-LIN-1VAR"],
            "state": ItemState.active,
            "origin": ItemOrigin.human,
            "a": 1.50,
            "b": 0.20,
        },
        {
            "tag": "item_active_12",
            "stem": "Solve for $y$: $\\frac{2y + 3}{5} = 7$.",
            "options": {"A": "16", "B": "32", "C": "14", "D": "19"},
            "key": "A",
            "rationale": "Multiply by 5: 2y + 3 = 35. Subtract 3: 2y = 32. y = 16.",
            "skills": ["ALG-LIN-1VAR", "FRAC-DIV"],
            "state": ItemState.active,
            "origin": ItemOrigin.human,
            "a": 1.65,
            "b": 0.50,
        },
        {
            "tag": "item_active_13",
            "stem": "Solve the system: $x + y = 10$ and $2x - y = 8$. Find $x$.",
            "options": {"A": "6", "B": "4", "C": "8", "D": "2"},
            "key": "A",
            "rationale": "Adding equations: 3x = 18 => x = 6.",
            "skills": ["ALG-LIN-SYS", "ALG-LIN-1VAR"],
            "state": ItemState.active,
            "origin": ItemOrigin.human,
            "a": 1.70,
            "b": 0.65,
        },
        {
            "tag": "item_active_14",
            "stem": "Solve for $(x, y)$ in $3x + 2y = 12$ and $y = x - 4$.",
            "options": {"A": "(4, 0)", "B": "(2, -2)", "C": "(0, 6)", "D": "(3, -1)"},
            "key": "A",
            "rationale": "Substitute y: 3x + 2(x - 4) = 12 => 5x - 8 = 12 => 5x = 20 => x = 4, y = 0.",
            "skills": ["ALG-LIN-SYS"],
            "state": ItemState.active,
            "origin": ItemOrigin.human,
            "a": 1.80,
            "b": 0.90,
        },
        {
            "tag": "item_active_15",
            "stem": "Expand the product of binomials: $(2x - 3)(x + 5)$.",
            "options": {
                "A": "2x^2 + 7x - 15",
                "B": "2x^2 - 7x - 15",
                "C": "2x^2 + 10x - 15",
                "D": "2x^2 + 7x + 15",
            },
            "key": "A",
            "rationale": "FOIL: 2x*x + 2x*5 - 3*x - 3*5 = 2x^2 + 10x - 3x - 15 = 2x^2 + 7x - 15.",
            "skills": ["ALG-POLY"],
            "state": ItemState.active,
            "origin": ItemOrigin.human,
            "a": 1.60,
            "b": 0.35,
        },
        {
            "tag": "item_active_16",
            "stem": "Factor completely: $x^2 - 9x + 20$.",
            "options": {
                "A": "(x - 4)(x - 5)",
                "B": "(x - 2)(x - 10)",
                "C": "(x + 4)(x + 5)",
                "D": "(x - 1)(x - 20)",
            },
            "key": "A",
            "rationale": "Numbers multiplying to 20 and adding to -9 are -4 and -5: (x - 4)(x - 5).",
            "skills": ["ALG-POLY"],
            "state": ItemState.active,
            "origin": ItemOrigin.human,
            "a": 1.75,
            "b": 0.55,
        },
        {
            "tag": "item_active_17",
            "stem": "Find the solutions to the equation $x^2 - 5x - 14 = 0$.",
            "options": {
                "A": "x = 7 and x = -2",
                "B": "x = -7 and x = 2",
                "C": "x = 14 and x = -1",
                "D": "x = 5 and x = -2",
            },
            "key": "A",
            "rationale": "Factor: (x - 7)(x + 2) = 0 => x = 7 or x = -2.",
            "skills": ["ALG-QUAD", "ALG-POLY"],
            "state": ItemState.active,
            "origin": ItemOrigin.human,
            "a": 1.85,
            "b": 0.85,
        },
        {
            "tag": "item_active_18",
            "stem": "Use the quadratic formula to solve $2x^2 - 4x - 3 = 0$. What is the discriminant?",
            "options": {"A": "40", "B": "8", "C": "-8", "D": "28"},
            "key": "A",
            "rationale": "b^2 - 4ac = (-4)^2 - 4(2)(-3) = 16 + 24 = 40.",
            "skills": ["ALG-QUAD"],
            "state": ItemState.active,
            "origin": ItemOrigin.human,
            "a": 1.95,
            "b": 1.30,
        },
        {
            "tag": "item_active_19",
            "stem": "Solve for roots of $3x^2 = 75$.",
            "options": {
                "A": "x = 5 and x = -5",
                "B": "x = 5 only",
                "C": "x = 25 and x = -25",
                "D": "x = 15 and x = -15",
            },
            "key": "A",
            "rationale": "Divide by 3: x^2 = 25. Taking square roots gives x = 5 and x = -5.",
            "skills": ["ALG-QUAD"],
            "state": ItemState.active,
            "origin": ItemOrigin.human,
            "a": 1.40,
            "b": -0.05,
        },
        {
            "tag": "item_active_20",
            "stem": "Simplify rational polynomial: $\\frac{x^2 - 16}{x + 4}$ for $x \\neq -4$.",
            "options": {"A": "x - 4", "B": "x + 4", "C": "x - 16", "D": "1"},
            "key": "A",
            "rationale": "Factor numerator: (x - 4)(x + 4) / (x + 4) = x - 4.",
            "skills": ["ALG-POLY", "FRAC-DIV"],
            "state": ItemState.active,
            "origin": ItemOrigin.human,
            "a": 1.90,
            "b": 1.15,
        },
        # --- 5 Pilot Items (origin='ai', awaiting calibration, rich lineage JSONB) ---
        {
            "tag": "item_pilot_01",
            "stem": "An airplane descends from 12,000 ft at a constant rate of 450 ft per minute. Which equation models height $h$ after $m$ minutes?",
            "options": {
                "A": "h = 12000 - 450m",
                "B": "h = 450m - 12000",
                "C": "h = 12000 + 450m",
                "D": "h = (12000 - m)/450",
            },
            "key": "A",
            "rationale": "Starting altitude is 12,000 and decreases by 450 per minute.",
            "skills": ["ALG-LIN-1VAR", "ALG-EXPR"],
            "state": ItemState.pilot,
            "origin": ItemOrigin.ai,
            "lineage": {
                "prompt_version": "v2.4-algebra-modeling",
                "solver_check_agreement": True,
                "screening_scores": {
                    "readability_fk": 8.1,
                    "distractor_plausibility": 0.94,
                    "grounding_relevance": 0.98,
                },
                "generator_model": "gemini-1.5-pro",
            },
            "a": None,
            "b": None,
        },
        {
            "tag": "item_pilot_02",
            "stem": "If $\\frac{3}{5}$ of a container holds 18 liters, what is the total capacity of the container?",
            "options": {
                "A": "30 liters",
                "B": "27 liters",
                "C": "10.8 liters",
                "D": "35 liters",
            },
            "key": "A",
            "rationale": "3/5 * C = 18 => C = 18 * 5/3 = 6 * 5 = 30.",
            "skills": ["FRAC-DIV", "ALG-LIN-1VAR"],
            "state": ItemState.pilot,
            "origin": ItemOrigin.ai,
            "lineage": {
                "prompt_version": "v2.4-fractions-wordprob",
                "solver_check_agreement": True,
                "screening_scores": {
                    "readability_fk": 7.4,
                    "distractor_plausibility": 0.91,
                    "grounding_relevance": 0.96,
                },
                "generator_model": "gemini-1.5-pro",
            },
            "a": None,
            "b": None,
        },
        {
            "tag": "item_pilot_03",
            "stem": "Find the vertex coordinates of the parabola defined by $y = x^2 - 6x + 5$.",
            "options": {"A": "(3, -4)", "B": "(-3, 32)", "C": "(3, 4)", "D": "(6, 5)"},
            "key": "A",
            "rationale": "Vertex x = -b/(2a) = 6/2 = 3. y = 3^2 - 6(3) + 5 = 9 - 18 + 5 = -4.",
            "skills": ["ALG-QUAD"],
            "state": ItemState.pilot,
            "origin": ItemOrigin.ai,
            "lineage": {
                "prompt_version": "v2.5-quadratics-vertex",
                "solver_check_agreement": True,
                "screening_scores": {
                    "readability_fk": 7.9,
                    "distractor_plausibility": 0.95,
                    "grounding_relevance": 0.97,
                },
                "generator_model": "gemini-1.5-pro",
            },
            "a": None,
            "b": None,
        },
        {
            "tag": "item_pilot_04",
            "stem": "Factor by grouping: $x^3 + 3x^2 + 2x + 6$.",
            "options": {
                "A": "(x^2 + 2)(x + 3)",
                "B": "(x^2 + 3)(x + 2)",
                "C": "(x + 2)^2(x + 3)",
                "D": "(x^2 + 6)(x + 1)",
            },
            "key": "A",
            "rationale": "x^2(x + 3) + 2(x + 3) = (x^2 + 2)(x + 3).",
            "skills": ["ALG-POLY"],
            "state": ItemState.pilot,
            "origin": ItemOrigin.ai,
            "lineage": {
                "prompt_version": "v2.5-polynomial-grouping",
                "solver_check_agreement": True,
                "screening_scores": {
                    "readability_fk": 7.2,
                    "distractor_plausibility": 0.89,
                    "grounding_relevance": 0.95,
                },
                "generator_model": "gemini-1.5-pro",
            },
            "a": None,
            "b": None,
        },
        {
            "tag": "item_pilot_05",
            "stem": "A bakery sells cookies for $2 and brownies for $3. If they sold 50 items and collected $120, how many brownies were sold?",
            "options": {"A": "20", "B": "30", "C": "15", "D": "25"},
            "key": "A",
            "rationale": "c + b = 50, 2c + 3b = 120. Multiply first by 2: 2c + 2b = 100. Subtract: b = 20.",
            "skills": ["ALG-LIN-SYS"],
            "state": ItemState.pilot,
            "origin": ItemOrigin.ai,
            "lineage": {
                "prompt_version": "v2.4-linear-systems-applied",
                "solver_check_agreement": True,
                "screening_scores": {
                    "readability_fk": 6.8,
                    "distractor_plausibility": 0.92,
                    "grounding_relevance": 0.99,
                },
                "generator_model": "gemini-1.5-pro",
            },
            "a": None,
            "b": None,
        },
        # --- 5 In-Review / Draft Items ---
        {
            "tag": "item_review_01",
            "stem": "Simplify the complex fraction: $\\frac{\\frac{1}{2} + \\frac{1}{3}}{\\frac{5}{6}}$.",
            "options": {"A": "1", "B": "5/6", "C": "25/36", "D": "6/5"},
            "key": "A",
            "rationale": "Numerator is 3/6 + 2/6 = 5/6. (5/6)/(5/6) = 1.",
            "skills": ["FRAC-ADD-SUB", "FRAC-DIV"],
            "state": ItemState.in_review,
            "origin": ItemOrigin.ai,
            "a": None,
            "b": None,
        },
        {
            "tag": "item_review_02",
            "stem": "Which value of $c$ makes the trinomial $x^2 + 8x + c$ a perfect square?",
            "options": {"A": "16", "B": "64", "C": "4", "D": "8"},
            "key": "A",
            "rationale": "(8/2)^2 = 4^2 = 16.",
            "skills": ["ALG-POLY"],
            "state": ItemState.in_review,
            "origin": ItemOrigin.human,
            "a": None,
            "b": None,
        },
        {
            "tag": "item_draft_01",
            "stem": "Solve for $z$: $4(z - 2) + 3 = 2(z + 5) - 1$.",
            "options": {"A": "8", "B": "6", "C": "7", "D": "9"},
            "key": "A",
            "rationale": "4z - 8 + 3 = 2z + 10 - 1 => 4z - 5 = 2z + 9 => 2z = 14 => z = 7 (mis-keyed draft under SME review).",
            "skills": ["ALG-LIN-1VAR"],
            "state": ItemState.draft,
            "origin": ItemOrigin.ai,
            "a": None,
            "b": None,
        },
        {
            "tag": "item_draft_02",
            "stem": "Find the discriminant of $x^2 - 6x + 9 = 0$.",
            "options": {"A": "0", "B": "36", "C": "18", "D": "-36"},
            "key": "A",
            "rationale": "b^2 - 4ac = 36 - 4(1)(9) = 0.",
            "skills": ["ALG-QUAD"],
            "state": ItemState.draft,
            "origin": ItemOrigin.human,
            "a": None,
            "b": None,
        },
        {
            "tag": "item_draft_03",
            "stem": "Subtract $(3x^2 - 2x + 4) - (x^2 + 5x - 7)$.",
            "options": {
                "A": "2x^2 - 7x + 11",
                "B": "2x^2 + 3x - 3",
                "C": "2x^2 - 7x - 3",
                "D": "4x^2 + 3x + 11",
            },
            "key": "A",
            "rationale": "3x^2 - x^2 - 2x - 5x + 4 - (-7) = 2x^2 - 7x + 11.",
            "skills": ["ALG-POLY"],
            "state": ItemState.draft,
            "origin": ItemOrigin.ai,
            "a": None,
            "b": None,
        },
    ]

    for itm in items_spec:
        item_id = deterministic_uuid(f"item:{itm['tag']}")
        skill_uuids = [skills_map[s_code].id for s_code in itm["skills"]]
        existing_item = session.scalar(select(Item).where(Item.id == item_id))

        if not existing_item:
            item_obj = Item(
                id=item_id,
                stem_md=itm["stem"],
                options=itm["options"],
                key=itm["key"],
                rationale_md=itm["rationale"],
                skill_ids=skill_uuids,
                state=itm["state"],
                origin=itm["origin"],
                lineage=itm.get("lineage")
                or {"generator": "seed", "seed_tag": itm["tag"]},
                a=itm["a"],
                b=itm["b"],
                param_version=1 if itm["a"] is not None else 0,
                exposure_count=15 if itm["state"] == ItemState.active else 0,
            )
            session.add(item_obj)
            session.flush()

            if itm["a"] is not None and itm["b"] is not None:
                existing_hist = session.scalar(
                    select(ItemParamHistory).where(
                        ItemParamHistory.item_id == item_id,
                        ItemParamHistory.version == 1,
                    )
                )
                if not existing_hist:
                    session.add(
                        ItemParamHistory(
                            item_id=item_id,
                            version=1,
                            a=itm["a"],
                            b=itm["b"],
                            n_responses=150,
                            point_biserial=0.45,
                        )
                    )

    session.flush()
    logger.info(
        "Seeded 30 items (20 active with IRT 2PL history, 5 pilot with AI lineage, 5 review/draft)."
    )

    # -------------------------------------------------------------------------
    # 5. Baseline Mastery Records for Learners
    # -------------------------------------------------------------------------
    for learner in learner_objects:
        for skill_code in ["ARITH-INT", "FRAC-BASIC", "FRAC-ADD-SUB", "ALG-EXPR"]:
            skill_obj = skills_map[skill_code]
            existing_m = session.scalar(
                select(Mastery).where(
                    Mastery.learner_id == learner.id,
                    Mastery.skill_id == skill_obj.id,
                )
            )
            if not existing_m:
                session.add(
                    Mastery(
                        learner_id=learner.id,
                        skill_id=skill_obj.id,
                        estimate=0.68,
                        confidence=0.85,
                        model_version="bkt-v1-baseline",
                    )
                )

    session.commit()
    logger.info("Database seeding successfully completed with full idempotency.")


def main() -> None:
    with SessionLocal() as session:
        seed_database(session)


if __name__ == "__main__":
    main()
