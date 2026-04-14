from flask import Flask, render_template, abort, request, session
import random

# ============================================
# IMPORT DATA
# ============================================
# school_data: όλη η δομή σχολείο -> τάξη -> μάθημα
# theoria: γενικό theory dictionary
# quiz_data: γενικό quiz dictionary
from data import school_data, theoria, quiz_data

# theory_map: αντιστοίχιση (class_key, subject_key) -> theory module
# quiz_map: αντιστοίχιση (class_key, subject_key) -> quiz module
from theory import theory_map
from quiz_data import quiz_map


# ============================================
# FLASK APP SETUP
# ============================================
# template_folder="templates" λέει στο Flask πού βρίσκονται τα html templates
app = Flask(__name__, template_folder="templates")

# secret_key χρειάζεται για να δουλεύει το session
# π.χ. για να κρατάμε προσωρινά τις randomized ερωτήσεις του quiz
app.secret_key = "mathsflow-secret-key"


# ============================================
# HELPER FUNCTIONS
# ============================================
# Αυτές οι συναρτήσεις αποφεύγουν να γράφουμε συνέχεια
# τον ίδιο κώδικα μέσα στα routes


def get_school(school_key):
    """
    Παίρνει το school από το school_data με βάση το school_key.

    Αν δεν υπάρχει, επιστρέφει 404.
    """
    school = school_data.get(school_key)
    if not school:
        abort(404)
    return school


def get_class_data(school_key, class_key):
    """
    Παίρνει:
    - το school
    - τα δεδομένα της τάξης

    Αν η τάξη δεν υπάρχει μέσα στο συγκεκριμένο school, επιστρέφει 404.
    """
    school = get_school(school_key)
    class_data = school["classes"].get(class_key)
    if not class_data:
        abort(404)
    return school, class_data


def get_subject_data(school_key, class_key, subject_key):
    """
    Παίρνει:
    - το school
    - την τάξη
    - το μάθημα

    Αν το μάθημα δεν υπάρχει, επιστρέφει 404.
    """
    school, class_data = get_class_data(school_key, class_key)
    subject_data = class_data["subjects"].get(subject_key)
    if not subject_data:
        abort(404)
    return school, class_data, subject_data


# ============================================
# HOME PAGE
# ============================================
# Route: /
# Δείχνει την αρχική σελίδα με όλες τις κατηγορίες σχολείων
@app.route("/")
def home():
    return render_template("index.html", schools=school_data)


# ============================================
# SCHOOL PAGE
# ============================================
# Route: /school/<school_key>
# Δείχνει τις τάξεις ενός σχολείου
# π.χ. ΓΕΛ -> Α, Β, Γ
@app.route("/school/<school_key>")
def school_page(school_key):
    school = get_school(school_key)
    return render_template(
        "school.html",
        school_key=school_key,
        school_name=school["name"],
        classes=school["classes"]
    )


# ============================================
# CLASS PAGE
# ============================================
# Route: /school/<school_key>/<class_key>
# Δείχνει τα μαθήματα μιας τάξης
# π.χ. Α' ΓΕΛ -> Άλγεβρα
@app.route("/school/<school_key>/<class_key>")
def class_page(school_key, class_key):
    school, class_data = get_class_data(school_key, class_key)
    return render_template(
        "class.html",
        school_key=school_key,
        class_key=class_key,
        school_name=school["name"],
        class_name=class_data["name"],
        subjects=class_data["subjects"]
    )


# ============================================
# SUBJECT PAGE
# ============================================
# Route: /school/<school_key>/<class_key>/<subject_key>
# Δείχνει τις ενότητες του μαθήματος
# π.χ. Άλγεβρα -> 2.1, 2.2, 2.3 ...
@app.route("/school/<school_key>/<class_key>/<subject_key>")
def subject_page(school_key, class_key, subject_key):
    school, class_data, subject_data = get_subject_data(school_key, class_key, subject_key)
    return render_template(
        "subject.html",
        school_key=school_key,
        class_key=class_key,
        subject_key=subject_key,
        school_name=school["name"],
        class_name=class_data["name"],
        subject_name=subject_data["name"],
        lessons=subject_data["lessons"]
    )


# ============================================
# STUDY PAGE
# ============================================
# Route: /study/<school_key>/<class_key>/<subject_key>/<lesson_id>
# Δείχνει τη θεωρία μιας συγκεκριμένης ενότητας
@app.route("/study/<school_key>/<class_key>/<subject_key>/<int:lesson_id>")
def study(school_key, class_key, subject_key, lesson_id):
    # παίρνουμε school, class και subject
    school, class_data, subject_data = get_subject_data(school_key, class_key, subject_key)

    # λίστα ενοτήτων του μαθήματος
    lessons = subject_data["lessons"]

    # έλεγχος αν το lesson_id είναι έγκυρο
    # lesson_id ξεκινά από 1, όχι από 0
    if lesson_id < 1 or lesson_id > len(lessons):
        abort(404)

    # βρίσκουμε το όνομα της ενότητας
    enotita = lessons[lesson_id - 1]

    # προσπαθούμε να βρούμε theory module για το συγκεκριμένο μάθημα
    # π.χ. ("a-gel", "algebra")
    subject_theory = theory_map.get((class_key, subject_key))

    # αν υπάρχει εξειδικευμένο theory module, παίρνουμε από εκεί τη θεωρία
    if subject_theory is not None:
        data = subject_theory.get(enotita, [])
    else:
        # αλλιώς fallback στο γενικό theoria dictionary
        data = theoria.get(enotita, [])

    # render της study page
    return render_template(
        "study/study.html",
        school_key=school_key,
        class_key=class_key,
        subject_key=subject_key,
        school_name=school["name"],
        class_name=class_data["name"],
        subject_name=subject_data["name"],
        enotita=enotita,
        theoria=data
    )


# ============================================
# QUIZ PAGE
# ============================================
# Route: /quiz/<school_key>/<class_key>/<subject_key>/<lesson_id>
# Methods: GET, POST
#
# GET:
# - εμφανίζει το quiz
# - κάνει shuffle στις επιλογές και στις ερωτήσεις
#
# POST:
# - διαβάζει τις απαντήσεις του χρήστη
# - υπολογίζει score
@app.route("/quiz/<school_key>/<class_key>/<subject_key>/<int:lesson_id>", methods=["GET", "POST"])
def quiz(school_key, class_key, subject_key, lesson_id):
    # παίρνουμε school, class και subject
    school, class_data, subject_data = get_subject_data(school_key, class_key, subject_key)

    # λίστα ενοτήτων
    lessons = subject_data["lessons"]

    # έλεγχος εγκυρότητας lesson_id
    if lesson_id < 1 or lesson_id > len(lessons):
        abort(404)

    # βρίσκουμε ποια ενότητα αντιστοιχεί
    enotita = lessons[lesson_id - 1]

    # προσπαθούμε να βρούμε εξειδικευμένο quiz module για το μάθημα
    subject_quiz = quiz_map.get((class_key, subject_key))

    # αν υπάρχει, παίρνουμε τις ερωτήσεις από εκεί
    if subject_quiz is not None:
        questions = subject_quiz.get(enotita, [])
    else:
        # αλλιώς fallback στο γενικό quiz_data
        questions = quiz_data.get(enotita, [])

    # ============================================
    # DIFFICULTY FILTER
    # ============================================
    # request.values δουλεύει και για GET και για POST
    # default = "all"
    difficulty = request.values.get("difficulty", "all")

    # αν έχει επιλεγεί φίλτρο, κρατάμε μόνο τις ερωτήσεις αυτού του επιπέδου
    if difficulty != "all":
        filtered_questions = [q for q in questions if q["difficulty"] == difficulty]
    else:
        filtered_questions = questions[:]

    # ============================================
    # SESSION KEY
    # ============================================
    # μοναδικό key για να κρατάμε στο session το randomized quiz
    # ώστε το POST να ελέγχει τις ίδιες ερωτήσεις/επιλογές που είδε ο χρήστης στο GET
    session_key = f"quiz_{school_key}_{class_key}_{subject_key}_{lesson_id}_{difficulty}"

    # ============================================
    # GET REQUEST
    # ============================================
    if request.method == "GET":
        randomized_questions = []

        # για κάθε ερώτηση:
        # - κάνουμε copy
        # - κάνουμε shuffle στις επιλογές
        for q in filtered_questions:
            q_copy = q.copy()
            q_copy["choices"] = q["choices"][:]
            random.shuffle(q_copy["choices"])
            randomized_questions.append(q_copy)

        # shuffle και στη σειρά των ερωτήσεων
        random.shuffle(randomized_questions)

        # αποθήκευση στο session
        session[session_key] = randomized_questions

        # πριν την υποβολή δεν υπάρχει score
        score = None
        user_answers = {}

    # ============================================
    # POST REQUEST
    # ============================================
    else:
        # παίρνουμε τις randomized ερωτήσεις από το session
        # αν για κάποιο λόγο δεν υπάρχουν, fallback στο filtered_questions
        randomized_questions = session.get(session_key, filtered_questions)

        score = 0
        user_answers = {}

        # ελέγχουμε κάθε απάντηση
        for i, q in enumerate(randomized_questions):
            selected = request.form.get(f"question_{i}")
            user_answers[str(i)] = selected

            if selected == q["answer"]:
                score += 1

    # συνολικός αριθμός ερωτήσεων
    total = len(randomized_questions)

    # render της quiz page
    return render_template(
        "quiz/quiz.html",
        school_key=school_key,
        class_key=class_key,
        subject_key=subject_key,
        school_name=school["name"],
        class_name=class_data["name"],
        subject_name=subject_data["name"],
        enotita=enotita,
        questions=randomized_questions,
        score=score,
        total=total,
        difficulty=difficulty,
        user_answers=user_answers
    )


# ============================================
# RUN APP
# ============================================
# Τρέχει το Flask app όταν ανοίγεις αυτό το αρχείο άμεσα
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)