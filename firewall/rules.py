# --- LLM Guard config ---

BANNED_INPUT_TOPICS = [
    "workout programming",
    "nutrition advice",
    "medical diagnosis",
    "injury treatment",
    "supplement recommendations",
    "relationship advice",
    "legal advice",
    "financial advice",
    "political opinions",
    "homework help",
    "coding help",
    "general knowledge",
    "career advice",
    "resume writing",
    "job applications",
]

# Zero-shot classifiers produce low absolute scores; 0.5 gives reliable
# signal without catching every tangentially adjacent message.
BAN_TOPICS_THRESHOLD = 0.5

BANNED_OUTPUT_TOPICS = [
    "other clients' schedules",
    "other clients' personal information",
    "admin personal details",
    "business revenue",
    "admin home address",
]

TOKEN_LIMIT = 500

# --- Donna custom detector patterns ---

IDENTITY_SPOOF_PATTERNS = [
    r"i am the (trainer|admin|owner|coach|manager)",
    r"i'm the (trainer|admin|owner|coach|manager)",
    r"as the (trainer|admin|owner|coach|manager)",
    r"this is (the trainer|the admin|the owner)",
    r"speaking as (your boss|your employer|the manager)",
]

SYSTEM_PROMPT_PATTERNS = [
    r"repeat (your|the) (instructions|prompt|system message|rules)",
    r"what (are|were) you (told|instructed|trained)",
    r"show me your (prompt|instructions|configuration|rules|system)",
    r"ignore (all )?(previous|prior|above) instructions",
    r"disregard (your )?(previous|prior) (instructions|training)",
    r"you are now (a |an )?(different|new|unrestricted)",
    r"pretend (you are|to be|you're) (not donna|a different|an unrestricted)",
    r"forget (everything|all instructions|your training)",
    r"developer mode",
    r"jailbreak",
    r"dan mode",
    r"do anything now",
]

EXFILTRATION_PATTERNS = [
    r"(list|show|tell me|give me|what are) (all |your |other )?(clients|users|members|people)",
    r"who (else )?(do you (train|work with)|is (a client|a member|scheduled))",
    r"(other|different) (clients?|members?|customers?|people('s)?)",
    r"(everyone'?s?|all) (schedule|session|appointment|booking)",
    r"how many (clients|members|people) (do you have|are there)",
]

BOOKING_CONFIRMATION_PATTERNS = [
    r"(i'?ve?|i have) (booked|scheduled|confirmed|reserved)",
    r"your (session|appointment|booking) (has been|is) (confirmed|booked|scheduled)",
    r"(booked|scheduled|confirmed) for",
    r"(see|expect) you (on|at)",
]

REDIRECT_OUT_OF_SCOPE = (
    "That's a bit outside what I can help with. I'm here to handle your "
    "scheduling and anything related to your sessions. Is there something "
    "I can sort out for you on that front?"
)

REDIRECT_MEDICAL = (
    "I'm not the right person for that one. For anything health or injury "
    "related, please reach out to a medical professional. Happy to help with "
    "your upcoming sessions though."
)

BLOCK_GENERIC_RESPONSE = (
    "I didn't quite get that. Want to try rephrasing, or is there something "
    "I can help you with regarding your sessions?"
)
