# --- LLM Guard config ---

# PERSON excluded: Donna legitimately addresses clients by name in every response.
# Keep financial/identity-theft-risk entities only.
SENSITIVE_ENTITY_TYPES = [
    "CREDIT_CARD", "CRYPTO", "EMAIL_ADDRESS", "IBAN_CODE", "IP_ADDRESS",
    "PHONE_NUMBER", "US_SSN", "US_BANK_NUMBER",
    "CREDIT_CARD_RE", "UUID", "EMAIL_ADDRESS_RE", "US_SSN_RE",
]

ADMIN_SENSITIVE_ENTITY_TYPES = [
    "CREDIT_CARD", "CRYPTO", "IBAN_CODE", "US_SSN", "US_BANK_NUMBER",
    "CREDIT_CARD_RE", "US_SSN_RE",
]

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

# Behavior when an input scanner raises: "closed" blocks the message, "open" lets it through.
INPUT_SCANNER_FAIL_MODE = {
    "token_limit": "open",
    "prompt_injection": "closed",
    "identity_spoof": "closed",
    "ban_topics": "open",
}

# --- Donna custom detector patterns ---

IDENTITY_SPOOF_PATTERNS = [
    r"i am the (trainer|admin|owner|coach|manager)",
    r"i'm the (trainer|admin|owner|coach|manager)",
    r"as the (trainer|admin|owner|coach|manager)",
    r"this is (the trainer|the admin|the owner)",
    r"speaking as (your boss|your employer|the manager)",
    r"\b(admin|owner|trainer|coach|manager|administrator) (here|speaking)\b",
    r"\b(i'?m|i am|this is|it'?s) (the |his |her |your |\w+'s )?(head |gym )?"
    r"(coach|trainer|owner|admin|administrator|manager|assistant|boss)\b",
    r"\b(message|instructions?|word) from (the |your )?(owner|admin|trainer|boss|manager)\b",
    r"\b(owner|admin|trainer|coach|manager|boss) (said|says|told|asked) (me |you |that )?"
    r"(i can|i may|i'm allowed|you can|you should|to (give|show|share|send|delete)|to cancel (everyone|all|every|other|\w+'s))",
    r"\bi (work|am working) for (the )?(gym |business )?(owner|trainer|manager|admin)\b",
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
    r"\byour new (role|instructions?|task|persona)\b",
    r"\bact as (a |an )?(terminal|shell|root|sudo|database|sql|unrestricted|different)\b",
    r"\b(dump|export|print|output) (the |all )?(raw )?(database|db|table|rows|records)\b",
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

REGISTRATION_CLAIM_PATTERNS = [
    r"(i'?ve?|i have) (registered|signed you up|added you)",
    r"you('re| are| have been) (now )?registered",
    r"registered you",
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


# Words a plain booking request is built from. The ML injection scanner false-blocks polite requests made only
# of these ("Please cancel my next session"). A message skips that one scanner only if EVERY word is in this
# set (and it is short), so no instruction-override or exfiltration sentence can qualify. All regex checks
# still run first.
SCHEDULING_VOCAB = frozenset("""
please kindly can could would will you i id i'd we me my the a an it is are am be to of for on at in from by
and or if so but also then next this that last first second third usual same one two option options
session sessions appointment appointments booking bookings time times slot slots class classes visit
cancel confirm confirmed reschedule rescheduled move book change add switch keep skip
monday tuesday wednesday thursday friday saturday sunday morning afternoon evening noon tonight tomorrow today
tomorrow's week weekend day days month january february march april may june july august september october
november december am pm free available open after before around about instead again still now
later sooner earlier yes no ok okay thanks thank works work good great fine sure go ahead do don't not need want
wanted like have has there how what when does did sorry late early soon back up out with
""".split())
MAX_PLAIN_REQUEST_WORDS = 25
