# -*- coding: utf-8 -*-
"""
AI服务封装层
功能：统一AI服务接口，支持Claude/OpenAI/本地模型切换
"""

import os
import json
import yaml
import hashlib
import asyncio
import logging
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod
import time

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AIProvider(ABC):
    """AI提供商抽象基类"""

    @abstractmethod
    async def chat(self, messages: List[Dict], system_prompt: str = None) -> str:
        """对话接口"""
        pass

    @abstractmethod
    async def get_embedding(self, text: str) -> List[float]:
        """获取文本向量"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """检查服务是否可用"""
        pass


class ClaudeProvider(AIProvider):
    """Claude API实现"""

    def __init__(self, config: Dict):
        self.config = config
        self.api_key = config.get('api_key', '') or os.environ.get('CLAUDE_API_KEY', '')
        self.model = config.get('model', 'claude-sonnet-4-20250514')
        self.max_tokens = config.get('max_tokens', 2048)
        self.temperature = config.get('temperature', 0.3)
        self.client = None

        if self.api_key:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=self.api_key)
                logger.info(f"Claude API initialized with model: {self.model}")
            except ImportError:
                logger.warning("anthropic package not installed, Claude API unavailable")

    def is_available(self) -> bool:
        return self.client is not None and bool(self.api_key)

    async def chat(self, messages: List[Dict], system_prompt: str = None) -> str:
        """调用Claude对话API"""
        if not self.is_available():
            raise RuntimeError("Claude API not available")

        try:
            # 转换消息格式
            claude_messages = []
            for msg in messages:
                role = msg.get('role', 'user')
                if role == 'system':
                    continue  # Claude使用单独的system参数
                claude_messages.append({
                    "role": role,
                    "content": msg.get('content', '')
                })

            # 调用API
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_prompt or "你是赛正慧采商城的智能助手。",
                messages=claude_messages,
                temperature=self.temperature
            )

            return response.content[0].text

        except Exception as e:
            logger.error(f"Claude API error: {e}")
            raise

    async def get_embedding(self, text: str) -> List[float]:
        """Claude暂不支持embedding，使用本地模型"""
        raise NotImplementedError("Claude does not provide embedding API")


class OpenAIProvider(AIProvider):
    """OpenAI GPT实现"""

    def __init__(self, config: Dict):
        self.config = config
        self.api_key = config.get('api_key', '') or os.environ.get('OPENAI_API_KEY', '')
        self.model = config.get('model', 'gpt-4o')
        self.max_tokens = config.get('max_tokens', 2048)
        self.temperature = config.get('temperature', 0.3)
        self.client = None

        if self.api_key:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=self.api_key)
                logger.info(f"OpenAI API initialized with model: {self.model}")
            except ImportError:
                logger.warning("openai package not installed")

    def is_available(self) -> bool:
        return self.client is not None and bool(self.api_key)

    async def chat(self, messages: List[Dict], system_prompt: str = None) -> str:
        """调用OpenAI对话API"""
        if not self.is_available():
            raise RuntimeError("OpenAI API not available")

        try:
            # 添加system消息
            formatted_messages = []
            if system_prompt:
                formatted_messages.append({"role": "system", "content": system_prompt})
            formatted_messages.extend(messages)

            response = self.client.chat.completions.create(
                model=self.model,
                messages=formatted_messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise

    async def get_embedding(self, text: str) -> List[float]:
        """获取文本向量"""
        if not self.is_available():
            raise RuntimeError("OpenAI API not available")

        try:
            response = self.client.embeddings.create(
                model="text-embedding-3-small",
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"OpenAI embedding error: {e}")
            raise


class LocalProvider(AIProvider):
    """本地模型实现（降级方案）"""

    def __init__(self, config: Dict):
        self.config = config
        self.model_name = config.get('model_name', 'paraphrase-multilingual-MiniLM-L12-v2')
        self.model = None
        self._initialized = False

        if config.get('enabled', True):
            self._init_model()

    def _init_model(self):
        """延迟初始化模型"""
        if self._initialized:
            return

        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(self.model_name)
            self._initialized = True
            logger.info(f"Local model initialized: {self.model_name}")
        except ImportError:
            logger.warning("sentence-transformers not installed, local model unavailable")
        except Exception as e:
            logger.error(f"Failed to load local model: {e}")

    def is_available(self) -> bool:
        if not self._initialized:
            self._init_model()
        return self.model is not None

    async def chat(self, messages: List[Dict], system_prompt: str = None) -> str:
        """本地模型不支持对话，返回提示"""
        return "本地模型暂不支持对话功能，请配置Claude或OpenAI API密钥以启用AI助手功能。"

    async def get_embedding(self, text: str) -> List[float]:
        """获取文本向量"""
        if not self.is_available():
            raise RuntimeError("Local model not available")

        embedding = self.model.encode(text)
        return embedding.tolist()


class EmbeddingCache:
    """语义向量缓存"""

    def __init__(self, cache_path: str = None):
        self.cache_path = cache_path or 'data/ai_cache.db'
        self.memory_cache = {}
        self._init_db()

    def _init_db(self):
        """初始化缓存数据库"""
        import sqlite3
        os.makedirs(os.path.dirname(self.cache_path) if os.path.dirname(self.cache_path) else '.', exist_ok=True)

        conn = sqlite3.connect(self.cache_path)
        cursor = conn.cursor()

        # 创建缓存表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text_hash TEXT UNIQUE,
                text TEXT,
                embedding BLOB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt_hash TEXT UNIQUE,
                prompt TEXT,
                response TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
        conn.close()

    def _hash_text(self, text: str) -> str:
        """生成文本哈希"""
        return hashlib.md5(text.encode('utf-8')).hexdigest()

    def get_embedding(self, text: str) -> Optional[List[float]]:
        """获取缓存的向量"""
        text_hash = self._hash_text(text)

        # 先查内存缓存
        if text_hash in self.memory_cache:
            return self.memory_cache[text_hash]

        # 查数据库
        import sqlite3
        import pickle

        try:
            conn = sqlite3.connect(self.cache_path)
            cursor = conn.cursor()
            cursor.execute('SELECT embedding FROM embeddings WHERE text_hash = ?', (text_hash,))
            result = cursor.fetchone()
            conn.close()

            if result:
                embedding = pickle.loads(result[0])
                self.memory_cache[text_hash] = embedding
                return embedding
        except Exception as e:
            logger.error(f"Cache read error: {e}")

        return None

    def save_embedding(self, text: str, embedding: List[float]):
        """保存向量到缓存"""
        text_hash = self._hash_text(text)

        # 保存到内存
        self.memory_cache[text_hash] = embedding

        # 保存到数据库
        import sqlite3
        import pickle

        try:
            conn = sqlite3.connect(self.cache_path)
            cursor = conn.cursor()
            cursor.execute(
                'INSERT OR REPLACE INTO embeddings (text_hash, text, embedding) VALUES (?, ?, ?)',
                (text_hash, text[:500], pickle.dumps(embedding))
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Cache save error: {e}")

    def get_response(self, prompt: str) -> Optional[str]:
        """获取缓存的响应"""
        prompt_hash = self._hash_text(prompt)

        import sqlite3
        try:
            conn = sqlite3.connect(self.cache_path)
            cursor = conn.cursor()
            cursor.execute('SELECT response FROM responses WHERE prompt_hash = ?', (prompt_hash,))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Response cache read error: {e}")
            return None

    def save_response(self, prompt: str, response: str):
        """保存响应到缓存"""
        prompt_hash = self._hash_text(prompt)

        import sqlite3
        try:
            conn = sqlite3.connect(self.cache_path)
            cursor = conn.cursor()
            cursor.execute(
                'INSERT OR REPLACE INTO responses (prompt_hash, prompt, response) VALUES (?, ?, ?)',
                (prompt_hash, prompt[:1000], response)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Response cache save error: {e}")

    def get_stats(self) -> Dict:
        """获取缓存统计"""
        import sqlite3
        try:
            conn = sqlite3.connect(self.cache_path)
            cursor = conn.cursor()

            cursor.execute('SELECT COUNT(*) FROM embeddings')
            embedding_count = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM responses')
            response_count = cursor.fetchone()[0]

            conn.close()

            return {
                'memory_cache_count': len(self.memory_cache),
                'embedding_count': embedding_count,
                'response_count': response_count
            }
        except Exception as e:
            return {'error': str(e)}


class AIService:
    """AI服务统一接口"""

    def __init__(self, config_path: str = None):
        self.config = self._load_config(config_path)
        self.cache = EmbeddingCache()
        self.providers = {}
        self.enabled = self.config.get('ai', {}).get('enabled', True)
        self.current_provider = None
        self.fallback_mode = False

        # 初始化提供商
        self._init_providers()

    def _load_config(self, config_path: str = None) -> Dict:
        """加载配置文件"""
        if config_path is None:
            # 默认配置路径
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_path = os.path.join(base_dir, 'config', 'ai_config.yaml')

        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f)
            except Exception as e:
                logger.error(f"Failed to load config: {e}")

        # 返回默认配置
        return {
            'ai': {'enabled': True, 'provider': 'claude'},
            'matching': {'weights': {'traditional': 0.35, 'semantic': 0.40, 'category': 0.15, 'brand': 0.10}},
            'assistant': {'enabled': True}
        }

    def _init_providers(self):
        """初始化AI提供商"""
        ai_config = self.config.get('ai', {})

        # 初始化Claude
        if ai_config.get('claude'):
            self.providers['claude'] = ClaudeProvider(ai_config['claude'])

        # 初始化OpenAI
        if ai_config.get('openai'):
            self.providers['openai'] = OpenAIProvider(ai_config['openai'])

        # 初始化本地模型
        if ai_config.get('local', {}).get('enabled', True):
            self.providers['local'] = LocalProvider(ai_config.get('local', {}))

        # 设置当前提供商
        provider_name = ai_config.get('provider', 'claude')
        if provider_name in self.providers and self.providers[provider_name].is_available():
            self.current_provider = provider_name
        else:
            # 尝试找到可用的提供商
            for name in ['claude', 'openai', 'local']:
                if name in self.providers and self.providers[name].is_available():
                    self.current_provider = name
                    break

        logger.info(f"Current AI provider: {self.current_provider}")

    def get_provider_name(self) -> str:
        """获取当前提供商名称"""
        return self.current_provider or 'none'

    def is_available(self) -> bool:
        """检查AI服务是否可用"""
        return self.enabled and self.current_provider is not None

    def get_provider(self) -> Optional[AIProvider]:
        """获取当前提供商实例"""
        if self.current_provider:
            return self.providers.get(self.current_provider)
        return None

    async def get_semantic_similarity(self, text1: str, text2: str) -> float:
        """计算语义相似度"""
        provider = self.get_provider()
        if not provider:
            return 0.0

        try:
            # 获取向量
            emb1 = await self._get_embedding_cached(text1)
            emb2 = await self._get_embedding_cached(text2)

            if emb1 and emb2:
                return self._cosine_similarity(emb1, emb2)
        except Exception as e:
            logger.error(f"Semantic similarity error: {e}")

        return 0.0

    async def _get_embedding_cached(self, text: str) -> Optional[List[float]]:
        """获取向量（带缓存）"""
        # 检查缓存
        cached = self.cache.get_embedding(text)
        if cached:
            return cached

        # 调用API获取
        provider = self.get_provider()
        if provider:
            try:
                embedding = await provider.get_embedding(text)
                self.cache.save_embedding(text, embedding)
                return embedding
            except Exception as e:
                logger.error(f"Get embedding error: {e}")

        return None

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似度"""
        import math
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    async def chat(self, messages: List[Dict], context: Dict = None) -> str:
        """对话接口"""
        if not self.is_available():
            return "AI服务暂不可用，请检查配置或稍后重试。"

        provider = self.get_provider()
        system_prompt = self.config.get('assistant', {}).get('system_prompt', '')

        # 添加上下文
        if context:
            context_info = self._build_context_info(context)
            system_prompt = system_prompt + "\n\n" + context_info

        # 检查缓存
        cache_key = json.dumps(messages, ensure_ascii=False)
        cached = self.cache.get_response(cache_key)
        if cached:
            return cached

        try:
            response = await provider.chat(messages, system_prompt)
            self.cache.save_response(cache_key, response)
            return response
        except Exception as e:
            logger.error(f"Chat error: {e}")
            self.fallback_mode = True
            return f"AI服务暂时不可用: {str(e)}"

    def _build_context_info(self, context: Dict) -> str:
        """构建上下文信息"""
        info_parts = []

        # 当前报价项
        if context.get('current_item'):
            item = context['current_item']
            info_parts.append(f"当前报价项: {item.get('name', '未知')}")

        # 匹配结果摘要
        if context.get('match_results'):
            results = context['match_results']
            total = len(results)
            matched = sum(1 for r in results if r.get('action') == 'select')
            info_parts.append(f"匹配情况: {matched}/{total} 项已匹配")

        # 商品库大小
        if context.get('products_count'):
            info_parts.append(f"商品库数量: {context['products_count']} 个商品")

        return "\n".join(info_parts) if info_parts else ""

    async def explain_match(self, query_item: Dict, match_result: Dict) -> Dict:
        """生成匹配解释"""
        if not self.is_available():
            return {'text': 'AI服务不可用', 'score_breakdown': {}}

        query_name = query_item.get('name', '')
        product_name = ''
        score_details = {}

        if match_result and match_result.get('product'):
            product_name = match_result['product'].get('name', '')
            score_details = match_result.get('score_details', {})

        prompt = f"""请解释以下商品匹配结果：

需求商品: {query_name}
匹配商品: {product_name}

评分详情:
- 文本相似度: {score_details.get('similarity', 0):.2f}
- 类型匹配: {score_details.get('type_match', 0):.2f}
- 关键词重叠: {score_details.get('keyword_overlap', 0):.2f}
- 品牌匹配: {score_details.get('brand_match', 0):.2f}

请用简洁的语言解释为什么这两个商品匹配（或不匹配），说明匹配的优势和可能的不足。"""

        messages = [{"role": "user", "content": prompt}]

        try:
            response = await self.chat(messages)
            return {
                'text': response,
                'score_breakdown': score_details
            }
        except Exception as e:
            return {'text': f'解释生成失败: {str(e)}', 'score_breakdown': score_details}

    async def recommend_alternatives(self, query_item: Dict, matched_products: List[Dict]) -> List[Dict]:
        """智能推荐替代品"""
        if not self.is_available():
            return []

        query_name = query_item.get('name', '')
        matched_names = [p.get('product', {}).get('name', '') for p in matched_products[:5]]

        prompt = f"""基于以下信息，分析需求商品并提供选择建议：

需求商品: {query_name}

已匹配的候选商品:
{chr(10).join([f'- {name}' for name in matched_names])}

请分析哪个商品最适合，并说明理由。如果都不太合适，说明需要寻找什么类型的商品。"""

        messages = [{"role": "user", "content": prompt}]

        try:
            response = await self.chat(messages)
            return [{
                'recommendation': response,
                'type': 'ai_analysis'
            }]
        except Exception as e:
            return []

    async def classify_product_category(self, product_name: str) -> Dict:
        """智能分类识别"""
        categories = self.config.get('knowledge', {}).get('categories', [])

        if not self.is_available() or not categories:
            # 降级到关键词匹配
            return self._keyword_classify(product_name, categories)

        prompt = f"""请将以下产品归类到合适的类别：

产品名称: {product_name}

可选类别: {', '.join(categories)}

只返回最合适的类别名称，不要解释。"""

        messages = [{"role": "user", "content": prompt}]

        try:
            response = await self.chat(messages)
            category = response.strip()
            return {
                'category': category if category in categories else '其他防护',
                'confidence': 0.8,
                'method': 'ai'
            }
        except Exception as e:
            return self._keyword_classify(product_name, categories)

    def _keyword_classify(self, product_name: str, categories: List[str]) -> Dict:
        """关键词分类（降级方案）"""
        category_keywords = {
            '手部防护': ['手套', '袖套', '护腕'],
            '头部防护': ['安全帽', '头盔', '面罩'],
            '呼吸防护': ['口罩', '防毒面具', '滤毒盒'],
            '足部防护': ['劳保鞋', '安全鞋', '雨鞋', '靴'],
            '眼面防护': ['眼镜', '护目镜', '面屏'],
            '听力防护': ['耳塞', '耳罩'],
            '身体防护': ['防护服', '雨衣', '反光衣'],
            '坠落防护': ['安全带', '救生衣']
        }

        for category, keywords in category_keywords.items():
            for kw in keywords:
                if kw in product_name:
                    return {'category': category, 'confidence': 0.7, 'method': 'keyword'}

        return {'category': '其他防护', 'confidence': 0.3, 'method': 'default'}

    async def recognize_brand(self, text: str) -> Dict:
        """智能品牌识别"""
        brands = self.config.get('knowledge', {}).get('brands', [])

        if not brands:
            return {'brand': '', 'confidence': 0}

        # 先用规则匹配
        text_lower = text.lower()
        for brand in brands:
            if brand.lower() in text_lower:
                return {'brand': brand, 'confidence': 0.9, 'method': 'rule'}

        # 如果规则没匹配到且AI可用，调用AI
        if self.is_available():
            prompt = f"""请从以下文本中识别品牌名称：

文本: {text}

已知品牌: {', '.join(brands[:10])}

如果有品牌，返回品牌名称；如果没有，返回"未知"。只返回品牌名称。"""

            messages = [{"role": "user", "content": prompt}]

            try:
                response = await self.chat(messages)
                brand = response.strip()
                if brand in brands:
                    return {'brand': brand, 'confidence': 0.8, 'method': 'ai'}
            except Exception:
                pass

        return {'brand': '', 'confidence': 0}

    def get_status(self) -> Dict:
        """获取服务状态"""
        return {
            'enabled': self.enabled,
            'provider': self.current_provider,
            'available': self.is_available(),
            'fallback_mode': self.fallback_mode,
            'cache_stats': self.cache.get_stats()
        }

    def toggle(self, enabled: bool):
        """开关AI功能"""
        self.enabled = enabled
        logger.info(f"AI {'enabled' if enabled else 'disabled'}")


# 全局AI服务实例
_ai_service_instance = None


def get_ai_service() -> AIService:
    """获取AI服务单例"""
    global _ai_service_instance
    if _ai_service_instance is None:
        _ai_service_instance = AIService()
    return _ai_service_instance