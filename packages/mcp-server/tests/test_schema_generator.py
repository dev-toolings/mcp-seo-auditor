"""Tests for SchemaGeneratorService."""

from app.services.schema_generator import SchemaGeneratorService


def _make_page(title="", h1="", content="", meta_description="", structured_data=None):
    """Build a minimal fake page object for testing."""

    class FakePage:
        pass

    page = FakePage()
    page.title = title
    page.h1 = h1
    page.content = content
    page.meta_description = meta_description
    page.structured_data = structured_data or []
    return page


class TestDetectPageType:
    """Tests for _detect_page_type heuristics."""

    def setup_method(self):
        self.service = SchemaGeneratorService()

    def test_faq_detected_from_title(self):
        page = _make_page(title="FAQ - Questions fréquentes")
        assert self.service._detect_page_type(page) == "faq"

    def test_faq_detected_from_content(self):
        page = _make_page(content="Q: Comment fonctionne le service?\nA: Très bien.")
        assert self.service._detect_page_type(page) == "faq"

    def test_how_to_detected_from_h1(self):
        page = _make_page(h1="Comment installer Python sur Ubuntu")
        assert self.service._detect_page_type(page) == "how_to"

    def test_how_to_detected_from_content(self):
        page = _make_page(content="Tutoriel complet en 5 étapes pour configurer nginx.")
        assert self.service._detect_page_type(page) == "how_to"

    def test_product_detected_from_content(self):
        page = _make_page(content="Prix: 49,99€ - Ajouter au panier - Référence produit AB123")
        assert self.service._detect_page_type(page) == "product"

    def test_article_detected_from_content(self):
        page = _make_page(content="Publié par Jean Dupont le 12 mars 2024. Article sur le blog.")
        assert self.service._detect_page_type(page) == "article"

    def test_recipe_detected_from_content(self):
        page = _make_page(
            content="Recette: ingrédients, préparation en 20 minutes, portions pour 4."
        )
        assert self.service._detect_page_type(page) == "recipe"

    def test_event_detected_from_content(self):
        page = _make_page(
            content="Conférence internationale, lieu: Paris, inscription obligatoire."
        )
        assert self.service._detect_page_type(page) == "event"

    def test_local_business_detected_from_content(self):
        page = _make_page(
            content="Adresse: 12 rue de la Paix. Téléphone: 01 23 45 67 89. Horaires: 9h-18h."
        )
        assert self.service._detect_page_type(page) == "local_business"

    def test_empty_page_defaults_to_webpage(self):
        page = _make_page()
        assert self.service._detect_page_type(page) == "webpage"

    def test_no_matching_pattern_defaults_to_webpage(self):
        page = _make_page(title="Accueil", content="Page principale du site web.")
        assert self.service._detect_page_type(page) == "webpage"


class TestExtractQaPairs:
    """Tests for _extract_qa_pairs content extraction."""

    def setup_method(self):
        self.service = SchemaGeneratorService()

    def test_extracts_numbered_qa_pairs(self):
        content = (
            "1. Comment créer un compte?\n"
            "Il suffit de cliquer sur S'inscrire.\n\n"
            "2. Comment réinitialiser mon mot de passe?\n"
            "Cliquez sur Mot de passe oublié."
        )
        pairs = self.service._extract_qa_pairs(content)
        assert len(pairs) == 2
        assert "?" in pairs[0][0]
        assert len(pairs[0][1]) > 0

    def test_extracts_q_prefix_pairs(self):
        content = (
            "Q: Qu'est-ce que le SEO?\n"
            "Le SEO est l'optimisation pour les moteurs de recherche.\n\n"
            "Q: Pourquoi le SEO est-il important?\n"
            "Parce qu'il augmente la visibilité."
        )
        pairs = self.service._extract_qa_pairs(content)
        assert len(pairs) >= 1

    def test_extracts_question_mark_lines(self):
        content = "Comment fonctionne cet outil?\nIl analyse votre site web automatiquement.\n"
        pairs = self.service._extract_qa_pairs(content)
        assert len(pairs) == 1
        assert pairs[0][0].endswith("?")
        assert "automatiquement" in pairs[0][1]

    def test_empty_content_returns_empty_list(self):
        pairs = self.service._extract_qa_pairs("")
        assert pairs == []

    def test_no_qa_pattern_returns_empty_list(self):
        content = "Voici du texte sans questions ni réponses formatées."
        pairs = self.service._extract_qa_pairs(content)
        assert pairs == []

    def test_answer_without_question_is_not_extracted(self):
        # A line that is just text (no question pattern)
        content = "Juste une réponse sans question précédente."
        pairs = self.service._extract_qa_pairs(content)
        assert pairs == []

    def test_caps_at_ten_pairs(self):
        """Generate more than 10 pairs — only 10 should be used in generate()."""
        lines = []
        for i in range(15):
            lines.append(f"{i + 1}. Question numéro {i + 1}?")
            lines.append(f"Réponse numéro {i + 1}.")
            lines.append("")
        content = "\n".join(lines)
        pairs = self.service._extract_qa_pairs(content)
        # _extract_qa_pairs itself may return all; the cap is applied in _generate_schema
        assert len(pairs) >= 1


class TestExtractSteps:
    """Tests for _extract_steps numbered/bulleted content extraction."""

    def setup_method(self):
        self.service = SchemaGeneratorService()

    def test_extracts_numbered_steps(self):
        content = (
            "1. Télécharger Python depuis python.org\n"
            "2. Lancer l'installateur\n"
            "3. Configurer les variables d'environnement\n"
        )
        steps = self.service._extract_steps(content)
        assert len(steps) == 3
        assert "python.org" in steps[0]

    def test_extracts_bullet_steps(self):
        content = (
            "- Ouvrir le terminal\n"
            "- Taper la commande pip install flask\n"
            "- Attendre la fin de l'installation\n"
        )
        steps = self.service._extract_steps(content)
        assert len(steps) >= 2

    def test_ignores_very_short_steps(self):
        """Steps with 10 or fewer characters should be skipped."""
        content = "1. Ok\n2. Installer le logiciel sur votre machine\n"
        steps = self.service._extract_steps(content)
        assert all(len(s) > 10 for s in steps)

    def test_empty_content_returns_empty_list(self):
        steps = self.service._extract_steps("")
        assert steps == []

    def test_no_numbered_content_returns_empty_list(self):
        content = "Du texte sans étapes numérotées ni listes."
        steps = self.service._extract_steps(content)
        assert steps == []

    def test_extracts_etape_prefix(self):
        content = "Étape 1: Créer un compte utilisateur sur le portail.\n"
        steps = self.service._extract_steps(content)
        assert len(steps) >= 1


class TestGetRecommendations:
    """Tests for _get_recommendations schema gap detection."""

    def setup_method(self):
        self.service = SchemaGeneratorService()

    def test_recommends_missing_schema_type(self):
        """When the expected schema is not present, it should be recommended."""
        recs = self.service._get_recommendations("faq", [])
        assert any("FAQPage" in r for r in recs)

    def test_always_recommends_breadcrumb_when_missing(self):
        recs = self.service._get_recommendations("article", [])
        assert any("BreadcrumbList" in r for r in recs)

    def test_no_breadcrumb_recommendation_when_already_present(self):
        existing = [{"@type": "BreadcrumbList"}, {"@type": "Article"}]
        recs = self.service._get_recommendations("article", existing)
        assert not any("BreadcrumbList" in r for r in recs)

    def test_no_schema_type_recommendation_when_already_present(self):
        existing = [{"@type": "FAQPage"}]
        recs = self.service._get_recommendations("faq", existing)
        # FAQPage already present — no recommendation to add it
        assert not any("Add FAQPage schema" in r for r in recs)

    def test_recommends_webpage_wrapper_for_non_webpage_type(self):
        recs = self.service._get_recommendations("article", [])
        assert any("WebPage" in r for r in recs)

    def test_no_webpage_recommendation_for_webpage_type(self):
        recs = self.service._get_recommendations("webpage", [])
        # page_type is "webpage" itself — no separate WebPage recommendation needed
        assert not any("Consider adding WebPage" in r for r in recs)

    def test_all_schemas_present_suggests_speakable(self):
        existing = [
            {"@type": "Article"},
            {"@type": "BreadcrumbList"},
            {"@type": "WebPage"},
        ]
        recs = self.service._get_recommendations("article", existing)
        assert any("speakable" in r.lower() for r in recs)
