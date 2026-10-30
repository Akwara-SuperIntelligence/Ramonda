/* Shared quiz widget for the Always-On Agents course.
   Markup:

   <div class="quiz" data-quiz>
     <p class="quiz-title">Check</p>
     <div class="quiz-q" data-answer="b">
       <p>Question?</p>
       <div class="options">
         <button class="option" data-opt="a"><span class="mark">A</span><span>...</span></button>
         ...
       </div>
       <div class="why"><b>Why:</b> ...</div>
     </div>
     ...
     <div class="quiz-foot"><span class="score">0 of 2 correct</span>
       <button class="reset" type="button">Reset</button></div>
   </div>
*/

(function () {
  function initQuiz(quiz) {
    const questions = Array.from(quiz.querySelectorAll(".quiz-q"));
    const scoreEl = quiz.querySelector(".score");
    const resetBtn = quiz.querySelector(".reset");
    const answered = new Map();

    function score() {
      let right = 0;
      questions.forEach((q) => {
        if (answered.get(q) === q.dataset.answer) right += 1;
      });
      if (scoreEl) {
        scoreEl.textContent =
          right + " of " + questions.length + " correct" + (right === questions.length ? " — solid" : "");
      }
    }

    questions.forEach((q) => {
      const options = Array.from(q.querySelectorAll(".option"));
      const why = q.querySelector(".why");
      options.forEach((btn) => {
        btn.addEventListener("click", () => {
          if (answered.has(q)) return;
          answered.set(q, btn.dataset.opt);
          const correct = q.dataset.answer;
          options.forEach((o) => {
            o.disabled = true;
            if (o.dataset.opt === correct) o.classList.add("is-correct");
            else if (o === btn) o.classList.add("is-wrong");
            o.setAttribute("aria-pressed", o === btn ? "true" : "false");
          });
          if (why) {
            why.classList.add("show");
            why.setAttribute("role", "status");
          }
          score();
        });
      });
    });

    if (resetBtn) {
      resetBtn.addEventListener("click", () => {
        answered.clear();
        questions.forEach((q) => {
          q.querySelectorAll(".option").forEach((o) => {
            o.disabled = false;
            o.classList.remove("is-correct", "is-wrong");
            o.removeAttribute("aria-pressed");
          });
          const why = q.querySelector(".why");
          if (why) why.classList.remove("show");
        });
        score();
      });
    }

    score();
  }

  document.querySelectorAll("[data-quiz]").forEach(initQuiz);
})();
