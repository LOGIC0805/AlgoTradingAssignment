import datetime
import pandas as pd
import exchange_calendars

# 获取公司数据库数据库接口
import connectorx as cx
## shstock: 公司 python module
from shstock.utils.globals import RUNTIME
from shstock.utils.dateutils import XSHG_IRREGULAR_CLOSED_DATES
## wind数据库接口
STOCK_DB_WIND = RUNTIME.get_sql_engine("wind")
## 朝阳永续数据库接口
STOCK_DB_ZYYX = RUNTIME.get_sql_engine("zyyx")


def get_exchange_trading_dates(start_date, end_date, exchange="XSHG"):
    if isinstance(start_date, str):
        start_date = datetime.datetime.strptime(start_date, "%Y%m%d")
        end_date = datetime.datetime.strptime(end_date, "%Y%m%d")
    start_date = start_date.strftime("%Y-%m-%d")
    end_date = end_date.strftime("%Y-%m-%d")
    trading_time = exchange_calendars.get_calendar(exchange).schedule
    trading_dates = list(trading_time.loc[start_date:end_date].index.date)

    irregular_dates = XSHG_IRREGULAR_CLOSED_DATES if exchange == "XSHG" else None
    if irregular_dates:
        trading_dates = filter(lambda x: x not in irregular_dates, trading_dates)
    return list(trading_dates)


def get_shifted_date(date: str, shift=2 * 365, date_type="calendar"):
    '''
    :param date: date, datetime, or str like "20221205" or "2022-12-05" original date
    :param shift: int shift days. positive means return is earlier than input; negative means return is later than input
    :param type: "trading" or "calendar"
    :return: str, eg. "20221205"
    eg.
        start_date = datetime.datetime(2022,12,1) # Thursday
        end_date = datetime.datetime(2022,12,2) # Friday
        data = get_feature("ep",start_date,end_date,engine = "cx")
        print(data)
        """            date       code     value
        0     2022-12-01  000001.SZ  0.172530
        1     2022-12-01  000002.SZ  0.103563
        2     2022-12-01  000004.SZ       NaN
        ...          ...        ...       ...
        10021 2022-12-02  873527.BJ  0.074743
        """
        keys = data.date.drop_duplicates()
        values = keys.apply(lambda x: get_shifted_date(x,-2,"trading"))
        date_dict = dict(zip(keys,values)) # create mapping to avoid redundantly shifting the same date
        data.date = data.date.map(date_dict)
        print(data)
        """           date       code     value
        0      20221205  000001.SZ  0.172530
        1      20221205  000002.SZ  0.103563
        2      20221205  000004.SZ       NaN
        ...         ...        ...       ...
        10021  20221206  873527.BJ  0.074743
        """
    '''
    if isinstance(date, datetime.datetime) or isinstance(date, datetime.date):
        date = date.strftime("%Y%m%d")
    if isinstance(date, str):
        date = date.replace("-", "")
    if date_type == "calendar":
        shifted_date = datetime.datetime.strptime(date, "%Y%m%d") - datetime.timedelta(
            days=shift
        )
    elif date_type == "trading":
        if shift > 0:
            start_date = datetime.datetime.strptime(date, "%Y%m%d") - datetime.timedelta(
                days=int(shift / 5 * 9 + 11)
            )
            end_date = datetime.datetime.strptime(date, "%Y%m%d")
            trading_dates = get_exchange_trading_dates(start_date, end_date)
            if end_date.date() == trading_dates[-1]:
                shift += 1
            shifted_date = trading_dates[-shift]
        else:
            start_date = datetime.datetime.strptime(date, "%Y%m%d")
            end_date = datetime.datetime.strptime(date, "%Y%m%d") - datetime.timedelta(
                days=int(shift / 5 * 9 - 11)
            )
            trading_dates = get_exchange_trading_dates(start_date, end_date)
            if start_date.date() != trading_dates[0]:
                shift += 1
            shifted_date = trading_dates[-shift]
    shifted_date = str(shifted_date).split()[0]
    shifted_date = "".join(shifted_date.split("-"))
    return shifted_date

# read existing feature
def get_feature(sig_name, start_date, end_date, env='feature_data_shared', output_type='stack', engine='cx'):
    if isinstance(start_date, datetime.datetime):
        start_date = start_date.strftime("%Y%m%d")
        end_date = end_date.strftime("%Y%m%d")
    sql = f"SELECT * FROM `{sig_name}` where date between '{start_date}' and '{end_date}'"

    if env == 'cache_data':
        get_id_sql = f"SELECT table_id FROM `table_ids` where feature_name = '{sig_name}'"
        id = cx.read_sql(RUNTIME.get_connectorx_conn(env), get_id_sql)
        if id.empty:
            print(f'The feature {sig_name} does not exist')
        else:
            id = id.iloc[-1, 0]
        sql = f"SELECT * FROM `{id}` where date between '{start_date}' and '{end_date}'"

    if engine == 'cx':
        feature = cx.read_sql(RUNTIME.get_connectorx_conn(env), sql)
    elif engine == 'pd':
        feature = pd.read_sql(sql, RUNTIME.get_sql_engine(env))

    if output_type == 'pivot':
        feature = feature.pivot(index='date', columns='code', values='value')
        feature.index = pd.to_datetime(feature.index)
    return feature
