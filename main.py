import sys
import json
import pulumi
import pulumi_aws as aws
from pulumi import automation as auto
import pymysql as mariadb

# This is our pulumi program in "inline function" form
def pulumi_program():
    default_vpc = aws.ec2.get_vpc(default=True)
    public_subnet_ids = aws.ec2.get_subnet_ids(vpc_id=default_vpc.id)
    subnet_group = aws.rds.SubnetGroup("db_subnet", subnet_ids=public_subnet_ids.ids)
    
    # make a public security group for our cluster for the migration
    security_group = aws.ec2.SecurityGroup(
        "public_group",
        ingress=[aws.ec2.SecurityGroupIngressArgs(
            protocol="-1",
            from_port=0,
            to_port=0,
            cidr_blocks=["0.0.0.0/0"]
        )],
        egress=[aws.ec2.SecurityGroupEgressArgs(
            protocol="-1",
            from_port=0,
            to_port=0,
            cidr_blocks=["0.0.0.0/0"]
        )])

    # example on, you should change this
    db_name = "your db"
    db_user = "your user"
    db_pass = "your password"
    db_engine = "mariadb"
    db_engine_version = "10.5.13"
    # db_engine = aws.rds.EngineType.AURORA_MYSQL
    # db_engine_version = "5.7.mysql_aurora.2.03.2"

    # provision our db for Cluster
    # rds = aws.rds.Cluster(
    #     "db",
    #     engine=db_engine,
    #     engine_version=db_engine_version,
    #     database_name=db_name,
    #     master_username=db_user,
    #     master_password=db_pass,
    #     skip_final_snapshot=True,
    #     db_subnet_group_name=subnet_group.name,
    #     vpc_security_group_ids=[security_group.id])

    # cluster_instance = aws.rds.ClusterInstance(
    #     "db_instance",
    #     cluster_identifier=rds.cluster_identifier,
    #     instance_class=aws.rds.InstanceType.T3_SMALL,
    #     engine=db_engine,
    #     engine_version=db_engine_version,
    #     publicly_accessible=True,
    #     db_subnet_group_name=subnet_group.name)

    rds = aws.rds.Instance(
        "db",
        identifier="iac-mariadb",
        engine=db_engine,
        engine_version=db_engine_version,
        instance_class="db.t2.micro",
        allocated_storage = 10,
        name=db_name,
        username=db_user,
        password=db_pass,
        skip_final_snapshot=True,
        publicly_accessible=True,
        db_subnet_group_name=subnet_group.name,
        vpc_security_group_ids=[security_group.id])

    pulumi.export("host", rds.endpoint)
    pulumi.export("db_name", db_name)
    pulumi.export("db_user", db_user)
    pulumi.export("db_pass", db_pass)


# To destroy our program, we can run python main.py destroy
destroy = False
args = sys.argv[1:]
if len(args) > 0:
    if args[0] == "destroy":
        destroy = True

project_name = "database_migration"
stack_name = "dev"

# create (or select if one already exists) a stack that uses our inline program
stack = auto.create_or_select_stack(
    stack_name=stack_name,
    project_name=project_name,
    program=pulumi_program)

print("successfully initialized stack")

# for inline programs, we must manage plugins ourselves
print("installing plugins...")
stack.workspace.install_plugin("aws", "v4.0.0")
print("plugins installed")

# set stack configuration specifying the AWS region to deploy
print("setting up config")
stack.set_config("aws:region", auto.ConfigValue(value="ap-northeast-2"))
print("config set")

print("refreshing stack...")
stack.refresh(on_output=print)
print("refresh complete")

if destroy:
    print("destroying stack...")
    stack.destroy(on_output=print)
    print("stack destroy complete")
    sys.exit()

print("updating stack...")
up_res = stack.up(on_output=print)
print(f"update summary: \n{json.dumps(up_res.summary.resource_changes, indent=4)}")
print(f"db host url: {up_res.outputs['host'].value}")

# init db
print("configuring db...")

print("creating table...")
conn = mariadb.connect(
    # erase the string ":3306"
    host=up_res.outputs['host'].value.split(":")[0],
    user=up_res.outputs['db_user'].value,
    password=up_res.outputs['db_pass'].value,
    database=up_res.outputs['db_name'].value)
cur = conn.cursor()
print("db configured!")

# make sure the table exists
create_table_query = """CREATE TABLE IF NOT EXISTS tab1(
    col1 int NOT NULL PRIMARY KEY,
    col2 int,
    col3 char(20),
    col4 char(100));
    """
cur.execute(create_table_query)
conn.commit()

# seed the table with some data to start
seed_table_query = """INSERT IGNORE INTO tab1 VALUES
    (1, 1, 'Purple', 'Purple'),
    (2, 2, 'Violet', 'Violet'),
    (3, 3, 'Plum', 'Plum');
"""
cur.execute(seed_table_query)
conn.commit()

print("rows inserted!")
print("querying to verify data...")

# read the data back
read_table_query = """SELECT COUNT(*) FROM tab1;"""
cur.execute(read_table_query)
result = cur.fetchone()
print(f"Result: {json.dumps(result)}")

conn.close()

print("database, table and rows successfully configured")
