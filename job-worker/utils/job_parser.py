"""
Job description parsing utilities.

This module provides functions for extracting structured information from
unstructured job posting text, including salary, experience level, remote type,
and technology stack.
"""

import re
from typing import Optional


# Common technology keywords organized by category
TECH_KEYWORDS: dict[str, list[str]] = {
    # Programming Languages
    "languages": [
        "Python", "JavaScript", "TypeScript", "Java", "C++", "C#", "Go", "Golang",
        "Rust", "Ruby", "PHP", "Swift", "Kotlin", "Scala", "R", "Julia",
        "Perl", "Haskell", "Elixir", "Clojure", "Lua", "Dart", "Objective-C",
    ],
    # Frontend
    "frontend": [
        "React", "Vue", "Angular", "Svelte", "Next.js", "Nuxt", "Remix",
        "HTML", "CSS", "SASS", "SCSS", "Less", "Tailwind", "Bootstrap",
        "jQuery", "Redux", "MobX", "Zustand", "GraphQL", "Apollo",
        "Webpack", "Vite", "Parcel", "Rollup",
    ],
    # Backend
    "backend": [
        "Node.js", "Express", "FastAPI", "Django", "Flask", "Spring",
        "Rails", "Laravel", "ASP.NET", ".NET", "Gin", "Echo", "Fiber",
        "NestJS", "Fastify", "Koa", "Hapi",
    ],
    # Databases
    "databases": [
        "PostgreSQL", "Postgres", "MySQL", "MongoDB", "Redis", "Elasticsearch",
        "DynamoDB", "Cassandra", "SQLite", "Oracle", "SQL Server", "MariaDB",
        "CockroachDB", "TimescaleDB", "InfluxDB", "Neo4j", "Supabase",
        "Firebase", "Firestore", "Prisma", "Drizzle",
    ],
    # Cloud & Infrastructure
    "cloud": [
        "AWS", "Amazon Web Services", "GCP", "Google Cloud", "Azure",
        "Kubernetes", "K8s", "Docker", "Terraform", "Pulumi", "CloudFormation",
        "Lambda", "EC2", "S3", "ECS", "EKS", "GKE", "AKS",
        "Vercel", "Netlify", "Heroku", "DigitalOcean", "Cloudflare",
    ],
    # DevOps & CI/CD
    "devops": [
        "Jenkins", "GitHub Actions", "GitLab CI", "CircleCI", "Travis CI",
        "ArgoCD", "Flux", "Ansible", "Chef", "Puppet", "Helm",
        "Prometheus", "Grafana", "Datadog", "New Relic", "Splunk",
        "ELK", "Logstash", "Kibana",
    ],
    # AI/ML
    "ai_ml": [
        "Machine Learning", "ML", "Deep Learning", "AI", "Artificial Intelligence",
        "TensorFlow", "PyTorch", "Keras", "scikit-learn", "sklearn",
        "Hugging Face", "Transformers", "LLM", "Large Language Models",
        "GPT", "OpenAI", "LangChain", "LlamaIndex", "RAG",
        "NLP", "Natural Language Processing", "Computer Vision", "CV",
        "MLOps", "MLflow", "Kubeflow", "SageMaker", "Vertex AI",
        "CUDA", "GPU", "JAX", "Pandas", "NumPy", "SciPy",
    ],
    # Data Engineering
    "data": [
        "Spark", "PySpark", "Hadoop", "Hive", "Airflow", "Dagster",
        "Prefect", "dbt", "Snowflake", "BigQuery", "Redshift", "Databricks",
        "Kafka", "RabbitMQ", "Pulsar", "Flink", "Beam", "Kinesis",
        "ETL", "ELT", "Data Pipeline",
    ],
    # Mobile
    "mobile": [
        "iOS", "Android", "React Native", "Flutter", "Xamarin",
        "SwiftUI", "Jetpack Compose", "Expo",
    ],
    # Other Tools
    "tools": [
        "Git", "GitHub", "GitLab", "Bitbucket", "Jira", "Confluence",
        "Slack", "Figma", "Notion", "Linear", "Asana", "Trello",
        "REST", "REST API", "gRPC", "WebSocket", "OAuth", "JWT",
        "Agile", "Scrum", "Kanban",
    ],
}

# Flatten all tech keywords for quick lookup
ALL_TECH_KEYWORDS: set[str] = set()
for category_keywords in TECH_KEYWORDS.values():
    ALL_TECH_KEYWORDS.update(kw.lower() for kw in category_keywords)


def parse_salary(text: str) -> tuple[Optional[int], Optional[int]]:
    """
    Extract salary range from text.

    Handles various formats:
    - "$100,000 - $150,000"
    - "$100k-$150k"
    - "$100K to $150K per year"
    - "$50/hour" (converts to annual)
    - "150000"

    Args:
        text: Text containing salary information.

    Returns:
        Tuple of (min_salary, max_salary) as integers, or (None, None) if not found.
    """
    if not text:
        return None, None

    text = text.lower().replace(",", "").replace(" ", "")

    # Check for hourly rate and convert to annual
    hourly_pattern = r"\$?(\d+(?:\.\d+)?)\s*(?:\/hr|\/hour|per\s*hour|hourly)"
    hourly_match = re.search(hourly_pattern, text)
    if hourly_match:
        hourly = float(hourly_match.group(1))
        # Assume 40 hours/week, 52 weeks/year
        annual = int(hourly * 40 * 52)
        return annual, annual

    # Pattern for ranges with various separators
    # Matches: $100k-$150k, $100,000 - $150,000, 100k to 150k, etc.
    range_patterns = [
        # $100k-$150k or $100K-$150K
        r"\$?(\d+(?:\.\d+)?)\s*[kK]\s*[-–—to]+\s*\$?(\d+(?:\.\d+)?)\s*[kK]",
        # $100,000 - $150,000 (already cleaned commas)
        r"\$?(\d{3,})\s*[-–—to]+\s*\$?(\d{3,})",
        # $100k - $150,000 (mixed formats)
        r"\$?(\d+(?:\.\d+)?)\s*[kK]?\s*[-–—to]+\s*\$?(\d+(?:\.\d+)?)\s*[kK]?",
    ]

    for pattern in range_patterns:
        match = re.search(pattern, text)
        if match:
            min_val = float(match.group(1))
            max_val = float(match.group(2))

            # Handle K notation
            if "k" in text[match.start():match.end()].lower():
                if min_val < 1000:
                    min_val *= 1000
                if max_val < 1000:
                    max_val *= 1000
            elif min_val < 1000 and max_val < 1000:
                # Likely K notation even without explicit K
                min_val *= 1000
                max_val *= 1000

            return int(min_val), int(max_val)

    # Single value patterns
    single_patterns = [
        r"\$(\d+(?:\.\d+)?)\s*[kK]",  # $150k
        r"\$(\d{3,})",  # $150000
        r"(\d+(?:\.\d+)?)\s*[kK]\s*(?:salary|annual|year)",  # 150k salary
    ]

    for pattern in single_patterns:
        match = re.search(pattern, text)
        if match:
            val = float(match.group(1))
            if "k" in text[match.start():match.end()].lower() or val < 1000:
                val *= 1000
            return int(val), int(val)

    return None, None


def parse_experience_level(title: str, description: str) -> str:
    """
    Determine experience level from job title and description.

    Levels:
    - entry: 0-2 years, junior, associate, new grad
    - mid: 2-5 years, standard engineer titles
    - senior: 5-8 years, senior titles
    - staff: 8-12 years, staff, principal, lead
    - executive: Director, VP, C-level

    Args:
        title: Job title.
        description: Job description text.

    Returns:
        Experience level string.
    """
    title_lower = title.lower()
    desc_lower = description.lower()[:2000]  # Check first 2000 chars

    # Executive level
    executive_keywords = [
        "chief", "cto", "ceo", "cfo", "coo", "vp ", "vice president",
        "director of engineering", "head of engineering", "head of",
        "engineering director",
    ]
    for kw in executive_keywords:
        if kw in title_lower:
            return "executive"

    # Staff/Principal level
    staff_keywords = [
        "staff", "principal", "distinguished", "fellow", "architect",
        "tech lead", "technical lead", "engineering lead",
    ]
    for kw in staff_keywords:
        if kw in title_lower:
            return "staff"

    # Senior level
    senior_keywords = ["senior", "sr.", "sr ", "lead"]
    for kw in senior_keywords:
        if kw in title_lower:
            return "senior"

    # Entry level
    entry_keywords = [
        "junior", "jr.", "jr ", "entry", "associate", "intern",
        "new grad", "graduate", "early career", "i ", " i,", " 1",
    ]
    for kw in entry_keywords:
        if kw in title_lower:
            return "entry"

    # Check description for years of experience
    years_patterns = [
        r"(\d+)\+?\s*(?:years?|yrs?)\s*(?:of)?\s*(?:experience|exp)",
        r"experience:\s*(\d+)\+?\s*(?:years?|yrs?)",
        r"minimum\s*(?:of)?\s*(\d+)\s*(?:years?|yrs?)",
        r"at\s*least\s*(\d+)\s*(?:years?|yrs?)",
    ]

    years_found = []
    for pattern in years_patterns:
        matches = re.findall(pattern, desc_lower)
        years_found.extend(int(y) for y in matches)

    if years_found:
        min_years = min(years_found)
        if min_years <= 2:
            return "entry"
        elif min_years <= 5:
            return "mid"
        elif min_years <= 8:
            return "senior"
        else:
            return "staff"

    # Default to mid-level if no clear indicators
    return "mid"


def parse_remote_type(title: str, location: str, description: str) -> str:
    """
    Determine remote work type from job information.

    Types:
    - remote: Fully remote position
    - hybrid: Mix of remote and in-office
    - onsite: Fully in-office
    - unknown: Cannot determine

    Args:
        title: Job title.
        location: Job location string.
        description: Job description text.

    Returns:
        Remote type string.
    """
    title_lower = title.lower()
    location_lower = location.lower()
    desc_lower = description.lower()[:3000]

    all_text = f"{title_lower} {location_lower} {desc_lower}"

    # Check for fully remote
    remote_indicators = [
        "remote", "work from home", "wfh", "work from anywhere",
        "fully remote", "100% remote", "remote-first", "remote first",
        "distributed team", "anywhere in",
    ]

    for indicator in remote_indicators:
        if indicator in all_text:
            # Check if it's explicitly NOT remote
            no_remote = [
                "no remote", "not remote", "on-site only", "onsite only",
                "office-based", "in-office only", "remote not available",
            ]
            for no_kw in no_remote:
                if no_kw in all_text:
                    return "onsite"
            return "remote"

    # Check for hybrid
    hybrid_indicators = [
        "hybrid", "flexible", "partial remote", "some remote",
        "remote optional", "work from office", "days in office",
        "2 days", "3 days", "4 days",
    ]

    for indicator in hybrid_indicators:
        if indicator in all_text:
            return "hybrid"

    # Check for on-site only
    onsite_indicators = [
        "on-site", "onsite", "in-office", "in office", "office-based",
        "office based", "must be local", "local only", "on site",
        "in-person", "in person",
    ]

    for indicator in onsite_indicators:
        if indicator in all_text:
            return "onsite"

    # Check location for hints
    if location_lower in ["remote", "anywhere", "worldwide", "united states"]:
        return "remote"

    return "unknown"


def extract_tech_stack(description: str) -> list[str]:
    """
    Extract mentioned technologies from job description.

    Uses a comprehensive list of tech keywords and performs case-insensitive
    matching with word boundary awareness.

    Args:
        description: Job description text.

    Returns:
        List of unique technology names found (original casing preserved).
    """
    if not description:
        return []

    found_tech: set[str] = set()

    for category, keywords in TECH_KEYWORDS.items():
        for keyword in keywords:
            # Create pattern with word boundaries
            # Handle special cases like C++, C#, .NET
            escaped = re.escape(keyword)
            pattern = rf"\b{escaped}\b"

            if re.search(pattern, description, re.IGNORECASE):
                found_tech.add(keyword)

    return sorted(list(found_tech))


def extract_years_experience(description: str) -> tuple[Optional[int], Optional[int]]:
    """
    Extract years of experience requirements from description.

    Args:
        description: Job description text.

    Returns:
        Tuple of (min_years, max_years) or (None, None) if not found.
    """
    desc_lower = description.lower()

    patterns = [
        # "5+ years of experience"
        r"(\d+)\+\s*(?:years?|yrs?)\s*(?:of)?\s*(?:experience|exp)",
        # "5-7 years of experience"
        r"(\d+)\s*[-–—to]+\s*(\d+)\s*(?:years?|yrs?)\s*(?:of)?\s*(?:experience|exp)",
        # "minimum 5 years"
        r"minimum\s*(?:of)?\s*(\d+)\s*(?:years?|yrs?)",
        # "at least 5 years"
        r"at\s*least\s*(\d+)\s*(?:years?|yrs?)",
        # "5 years minimum"
        r"(\d+)\s*(?:years?|yrs?)\s*(?:minimum|min)",
        # "experience: 5 years"
        r"experience:\s*(\d+)\s*(?:years?|yrs?)",
    ]

    min_years = None
    max_years = None

    for pattern in patterns:
        matches = re.findall(pattern, desc_lower)
        for match in matches:
            if isinstance(match, tuple):
                # Range pattern
                min_years = int(match[0]) if min_years is None else min(min_years, int(match[0]))
                max_years = int(match[1]) if max_years is None else max(max_years, int(match[1]))
            else:
                # Single value
                val = int(match)
                min_years = val if min_years is None else min(min_years, val)
                max_years = val if max_years is None else max(max_years, val)

    return min_years, max_years


def extract_education_requirements(description: str) -> Optional[str]:
    """
    Extract education requirements from job description.

    Args:
        description: Job description text.

    Returns:
        Education level string or None.
    """
    desc_lower = description.lower()

    education_levels = [
        ("phd", ["ph.d", "phd", "doctorate", "doctoral"]),
        ("masters", ["master's", "masters", "m.s.", "ms ", "mba", "m.a."]),
        ("bachelors", ["bachelor's", "bachelors", "b.s.", "bs ", "b.a.", "ba ",
                      "undergraduate degree", "4-year degree", "four year degree"]),
        ("associates", ["associate's", "associates", "a.s.", "a.a.", "2-year degree"]),
        ("high_school", ["high school", "ged", "diploma"]),
    ]

    # Also check for "or equivalent experience" modifier
    equivalent_patterns = [
        "or equivalent", "or related", "or similar", "preferred",
        "degree preferred", "not required",
    ]
    has_equivalent = any(p in desc_lower for p in equivalent_patterns)

    for level, keywords in education_levels:
        for kw in keywords:
            if kw in desc_lower:
                # Check context - is it required or preferred?
                pattern = rf"(?:require|must have|need).{{0,50}}{re.escape(kw)}"
                if re.search(pattern, desc_lower):
                    return f"{level}_required"

                if has_equivalent:
                    return f"{level}_preferred"

                return level

    return None


def determine_job_category(title: str, description: str = "") -> str:
    """
    Determine the job category based on title and description.

    Categories:
    - ai_ml: AI/ML Engineer, Data Scientist, ML Platform
    - full_stack: Full Stack Engineer
    - backend: Backend Engineer, API Engineer
    - frontend: Frontend Engineer, UI Engineer
    - devops: DevOps, SRE, Platform Engineer, Infrastructure
    - data: Data Engineer, Analytics Engineer
    - mobile: iOS, Android, Mobile Engineer
    - security: Security Engineer
    - management: Engineering Manager, Tech Lead, Director
    - other: Uncategorized

    Args:
        title: Job title
        description: Job description (optional, used for context)

    Returns:
        Category string
    """
    title_lower = title.lower()
    desc_lower = (description or "").lower()

    # AI/ML patterns
    ai_ml_patterns = [
        "machine learning", "ml engineer", "ai engineer", "artificial intelligence",
        "data scientist", "deep learning", "nlp", "computer vision", "cv engineer",
        "llm", "llm engineer", "ml platform", "mlops", "ai/ml", "ai-enabled",
        "agi", "research scientist", "research engineer", "ai solution", "ai architect",
        "hpc & ai", "ai systems",
    ]
    if any(p in title_lower for p in ai_ml_patterns):
        return "ai_ml"

    # Management patterns
    mgmt_patterns = [
        "engineering manager", "eng manager", "tech lead", "technical lead",
        "director of engineering", "vp of engineering", "head of engineering",
        "cto", "chief technology", "team lead", "staff engineer", "principal engineer",
    ]
    if any(p in title_lower for p in mgmt_patterns):
        return "management"

    # DevOps/Platform patterns
    devops_patterns = [
        "devops", "sre", "site reliability", "platform engineer", "infrastructure",
        "cloud engineer", "systems engineer", "release engineer", "build engineer",
    ]
    if any(p in title_lower for p in devops_patterns):
        return "devops"

    # Data Engineering patterns
    data_patterns = [
        "data engineer", "analytics engineer", "data platform", "data infrastructure",
        "etl", "elt", "pipeline engineer", "data architect",
    ]
    if any(p in title_lower for p in data_patterns):
        return "data"

    # Mobile patterns
    mobile_patterns = [
        "mobile engineer", "ios engineer", "android engineer", "mobile developer",
        "ios developer", "android developer", "react native", "flutter",
    ]
    if any(p in title_lower for p in mobile_patterns):
        return "mobile"

    # Security patterns
    security_patterns = [
        "security engineer", "security architect", "appsec", "application security",
        "cybersecurity", "infosec", "security analyst",
    ]
    if any(p in title_lower for p in security_patterns):
        return "security"

    # Frontend patterns
    frontend_patterns = [
        "frontend", "front-end", "front end", "ui engineer", "ui developer",
        "react engineer", "vue engineer", "angular engineer",
    ]
    if any(p in title_lower for p in frontend_patterns):
        return "frontend"

    # Backend patterns
    backend_patterns = [
        "backend", "back-end", "back end", "api engineer", "server engineer",
        "services engineer",
    ]
    if any(p in title_lower for p in backend_patterns):
        return "backend"

    # Full Stack patterns (check after frontend/backend)
    fullstack_patterns = [
        "full stack", "fullstack", "full-stack", "software engineer",
        "software developer", "web developer", "application developer",
    ]
    if any(p in title_lower for p in fullstack_patterns):
        return "full_stack"

    # Check description for context clues if title is ambiguous
    if "react" in desc_lower or "frontend" in desc_lower:
        return "frontend"
    if "api" in desc_lower and "backend" in desc_lower:
        return "backend"

    return "other"


def normalize_job_title(title: str) -> str:
    """
    Normalize job title for comparison and deduplication.

    Args:
        title: Original job title.

    Returns:
        Normalized title string.
    """
    # Lowercase
    normalized = title.lower()

    # Remove common suffixes/prefixes
    removals = [
        r"\s*-\s*remote$", r"\s*\(remote\)$", r"^\[.*?\]\s*",
        r"\s*-\s*hybrid$", r"\s*\(hybrid\)$",
        r"\s*-\s*urgent$", r"\s*\(urgent\)$",
        r"\s*-\s*immediate\s*start$",
    ]

    for pattern in removals:
        normalized = re.sub(pattern, "", normalized, flags=re.IGNORECASE)

    # Standardize common abbreviations
    replacements = {
        r"\bsr\.?\b": "senior",
        r"\bjr\.?\b": "junior",
        r"\bswe\b": "software engineer",
        r"\bsde\b": "software development engineer",
        r"\bml\b": "machine learning",
        r"\bai\b": "artificial intelligence",
        r"\bfe\b": "frontend",
        r"\bbe\b": "backend",
        r"\bfull\s*stack\b": "fullstack",
    }

    for pattern, replacement in replacements.items():
        normalized = re.sub(pattern, replacement, normalized)

    # Clean up whitespace
    normalized = re.sub(r"\s+", " ", normalized).strip()

    return normalized


def calculate_title_similarity(title1: str, title2: str) -> float:
    """
    Calculate similarity between two job titles.

    Uses normalized comparison and word overlap.

    Args:
        title1: First job title.
        title2: Second job title.

    Returns:
        Similarity score from 0.0 to 1.0.
    """
    norm1 = normalize_job_title(title1)
    norm2 = normalize_job_title(title2)

    # Exact match after normalization
    if norm1 == norm2:
        return 1.0

    # Word overlap (Jaccard similarity)
    words1 = set(norm1.split())
    words2 = set(norm2.split())

    intersection = len(words1 & words2)
    union = len(words1 | words2)

    if union == 0:
        return 0.0

    return intersection / union
