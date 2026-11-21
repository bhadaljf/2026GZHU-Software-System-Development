from src.gen_data import generate
from src.validate import validate
from src.store import connect, init_db, write_dataset

# 1. 生成small数据集，seed=42固定，保证每次生成一模一样（R8可复现）
ds = generate(scale="small", out_dir="./data/small", seed=42)
# 2. 执行R39校验规则
issues = validate(ds)
# 筛选error级别的异常（warning放过，W1只拦截error）
err_list = [x for x in issues if x.level == "error"]
print(f"error数量:{len(err_list)}")
# 断言：只要有error，直接抛出异常，自测失败
assert len(err_list) == 0, f"校验error不为0:{err_list}"

# 3. 初始化数据库（全新空库，会删除旧test_small.db）
init_db("test_small.db", schema_path="db/schema.sql")
# 4. 打开数据库连接
conn = connect("test_small.db")
# 5. 把整个Dataset写入sqlite
write_dataset(conn, ds)
conn.close()

print("✅W1自测完成:small数据集【生成-校验-入库】链路正常，可交付引擎开发")
