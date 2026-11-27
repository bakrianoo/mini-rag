from typing import Literal
from pydantic import BaseModel


class Options(BaseModel):
    A: str
    B: str
    C: str
    D: str


class QuizQuestion(BaseModel):
    question: str
    options: Options
    correct_answer: Literal["A", "B", "C", "D"]
    explanation: str


class QuizOutput(BaseModel):
    questions: list[QuizQuestion]

class AnswerQuestionRequest(BaseModel):
    question_id: str
    answer: Literal["A", "B", "C", "D"]