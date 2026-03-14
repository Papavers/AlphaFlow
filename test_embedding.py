from dotenv import load_dotenv
load_dotenv('.env')

from rdagent.oai.llm_utils import APIBackend


def main():
    api = APIBackend()
    texts = ["你好，世界", "这是一个测试句子"]
    try:
        embeddings = api.create_embedding(texts)
        print("成功获取 embeddings，数量：", len(embeddings))
        print("每项向量长度：", len(embeddings[0]) if embeddings else 0)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print("创建 embedding 失败，异常：", repr(e))


if __name__ == "__main__":
    main()
