# test_w2.py W2完整自测脚本
from src.store import connect, init_db, write_dataset
from src.gen_data import generate, save_dataset, load_dataset
from src.validate import validate

DB_PATH = "./test.db"

def test_small_case():
    """测试small：生成、校验、入库、json序列化/反序列化回归"""
    print("=====【1】small数据集测试 =====")
    # 初始化数据库，会删除旧test.db
    init_db(db_path=DB_PATH)
    conn = connect(DB_PATH)

    # 生成small
    ds_small = generate(scale="small", out_dir="./data/small", seed=20261119)
    print(f"考生数量:{len(ds_small.students)}")

    # 内存校验
    errs = validate(ds_small)
    if len(errs) > 0:
        print(f"small校验失败，共{len(errs)}条错误")
        for e in errs:
            print(f"[{e.table}] key={e.key} | {e.message}")
        conn.close()
        return False
    print("small内存校验全部通过")

    # 入库
    write_err = write_dataset(conn, ds_small)
    if len(write_err) > 0:
        print("small入库校验失败")
        conn.close()
        return False
    print("small数据集入库成功")

    # 序列化保存 + 反序列化加载（契约接口save_dataset / load_dataset）
    save_dataset(ds_small, out_dir="./data/small")
    ds_reload = load_dataset("./data/small")
    print("small json序列化、反序列化成功")

    conn.close()
    return True


def test_large_light():
    """
    large轻量调试
    不修改config/rules.toml磁盘文件，通过monkey‑patch内存替换tomllib.load返回值用于本地自测。
    正式业务运行仍然读取toml原始磁盘配置。
    注意：generate接口返回完整Dataset对象，全部数据驻留内存，请勿直接使用150000考生进行单元测试。
    """
    import src.gen_data
    import tomllib

    # 读取磁盘真实配置
    with open("config/rules.toml", "rb") as f:
        real_cfg = tomllib.load(f)

    # 在内存拷贝一份，修改规模参数
    patch_cfg = dict(real_cfg)
    patch_cfg["data"] = {
        "seed": real_cfg["data"]["seed"],
        "students": 3000,
        "middle_schools": 50,
        "high_schools": 15
    }

    # 保存原始load函数
    original_tomllib_load = tomllib.load

    def patched_load(fp):
        # 不管读哪个文件，直接返回我们修改好的内存配置字典
        return patch_cfg

    # monkey‑patch：替换gen_data模块用到的tomllib.load
    src.gen_data.tomllib.load = patched_load
    try:
        print("\n=====【2】large轻量模式测试（内存临时覆盖参数，磁盘toml保持不变） =====")
        ds_large = generate(scale="large", out_dir="./data/large", seed=20261119)
        print(f"large考生数量:{len(ds_large.students)}")

        errs = validate(ds_large)
        if len(errs) > 0:
            print(f"large校验失败，共{len(errs)}条错误")
            for e in errs:
                print(f"[{e.table}] key={e.key} | {e.message}")
            return False
        print("large轻量内存校验全部通过")
        return True
    finally:
        # 恢复原始函数，消除patch，不污染后续逻辑
        src.gen_data.tomllib.load = original_tomllib_load


if __name__ == "__main__":
    ok1 = test_small_case()
    ok2 = test_large_light()
    if ok1 and ok2:
        print("\nW2全部自测用例执行完毕！")
    else:
        print("\n存在测试失败，请排查代码")
