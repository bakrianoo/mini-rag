import os
import logging
from string import Template

class TemplateParser:
    def __init__(self, default_language: str = "en"):
        self.current_path = os.path.dirname(os.path.abspath(__file__))
        self.default_language = default_language
        self.logger = logging.getLogger(__name__)

        language_path = os.path.join(
            self.current_path,
            "locales",
            default_language
        )

        if not default_language or not os.path.exists(language_path):
            self.logger.error(
                "Language not supported, 'en' has been set as default"
            )
            self.default_language = "en"

        self.language = self.default_language

    def set_language(self, language: str):
        language_path = os.path.join(
            self.current_path,
            "locales",
            language
        )

        if not language or not os.path.exists(language_path):
            self.language = self.default_language
            return None

        self.language = language

    def get(self, group: str, key: str, vars: dict | None = None):
        if not group or not key:
            return None

        if vars is None:
            vars = {}

        targeted_language = self.language

        group_path = os.path.join(
            self.current_path,
            "locales",
            targeted_language,
            f"{group}.py"
        )

        if not os.path.exists(group_path):
            targeted_language = self.default_language

            group_path = os.path.join(
                self.current_path,
                "locales",
                targeted_language,
                f"{group}.py"
            )

        if not os.path.exists(group_path):
            return None

        module = __import__(
            f"stores.llm.templates.locales.{targeted_language}.{group}",
            fromlist=[group]
        )

        key_attribute = getattr(module, key)

        if key_attribute is None:
            return None

        return key_attribute.safe_substitute(vars)

        


    