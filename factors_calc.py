import os
import pandas as pd
import numpy as np
import factors_utils as utils

# 获取公司数据库数据库接口
## shstock: 公司 python module
from shstock.utils.globals import RUNTIME
## 日频数据库
STOCK_DB_WIND = RUNTIME.get_sql_engine("wind_new")
## 分钟频数据文件
root_dir = RUNTIME.get_path("L1_data_dir")+'\\L1_{}min\\{}_{}min.csv'


def LogVol_10Tail_1min(start_date, end_date, freq=1, quantile=0.1):
    '''
    兴业证券 - 高频研究系列四—成交量分布中的 Alpha
    LogVol_10Tail_1min: 日内1分钟对数成交量厚尾 10%分位数以下占比 [*反向]

    :param start_date: 开始日期
    :param end_date: 结束日期
    :param freq: 数据频率
    :param quantile: 分位数
    :return:
    '''

    def _get_factor(group):
        flag = group['log_volume'] < group['log_volume'].quantile(quantile)
        return group.loc[flag]['log_volume'].sum() / group['log_volume'].sum()

    # 获取 freq = 1 分钟频率量价数据
    start_date = start_date.strftime('%Y%m%d')
    end_date = end_date.strftime('%Y%m%d')
    date_list = [date.strftime('%Y%m%d') for date in utils.get_exchange_trading_dates(start_date, end_date)]
    df = pd.DataFrame()
    for date in date_list:
        path = root_dir.format(str(freq), date, str(freq))
        if not os.path.exists(path):
            continue
        data = pd.read_csv(path)

        # 实现因子逻辑
        data['log_volume'] = np.log(data['volume'])
        data['log_volume'] = data['log_volume'].replace(-np.inf, 0)
        logvol_factor = data.groupby('windCode').apply(_get_factor)
        logvol_factor = logvol_factor.rename(date, inplace=True)
        df = pd.concat([df, logvol_factor], axis=1)

    df = df.T
    df = df.loc[start_date: end_date, :]
    df.index = pd.to_datetime(df.index)
    df *= -1
    return df.replace([np.inf, -np.inf], np.nan)


def Vol_MaxStd_1min(start_date, end_date, freq=1, bootstrap_num=100, window=15):
    '''
    兴业证券 - 高频研究系列四—成交量分布中的 Alpha
    Vol_MaxStd_1min: 日内成交量极大值标准差 [*反向]

    :param start_date: 开始时间
    :param end_date: 结束时间
    :param freq: 数据频率
    :param bootstrap_num: 重抽样次数
    :param window: 滚动窗口大小
    :return:
    '''

    def _bootstrap_max(x):
        return np.random.choice(x, size=len(x), replace=True).max()

    # 获取 freq = 1 分钟频率量价数据
    start_date = start_date.strftime('%Y%m%d')
    end_date = end_date.strftime('%Y%m%d')
    start_date_ago = utils.get_shifted_date(start_date, window, date_type='trading')
    date_list = [date.strftime('%Y%m%d') for date in utils.get_exchange_trading_dates(start_date_ago, end_date)]
    df = pd.DataFrame()
    for date in date_list:
        path = root_dir.format(str(freq), date, str(freq))
        if not os.path.exists(path):
            continue
        data = pd.read_csv(path)

        # 实现因子逻辑
        volume = data.pivot(index="tradingMinute", columns="windCode", values="volume")
        vol_bootstrap_max = volume.apply(lambda x: [_bootstrap_max(x) for i in range(bootstrap_num)], axis=0, result_type='expand')
        vol_bootstrap_max = vol_bootstrap_max.std()
        vol_bootstrap_max = vol_bootstrap_max.rename(date, inplace=True)
        df = pd.concat([df, vol_bootstrap_max], axis=1)

    df = df.T
    df = df.rolling(window).std()
    df = df.loc[start_date: end_date, :]
    df.index = pd.to_datetime(df.index)
    df *= -1
    return df.replace([np.inf, -np.inf], np.nan)


def VCV_Daily(start_date, end_date, rolling_window=20):
    '''
    招商证券 - 高频寻踪：再觅知情交易者的踪迹
    VCV_Daily_Month: 交易量标准差/均值（日频数据，月度计算） [*反向]
    VCV_Daily_Week: 交易量标准差/均值（日频数据，周度计算） [*反向]

    :param start_date: 开始时间
    :param end_date: 结束时间
    :param rolling_window: 滚动窗口大小 {VCV_Daily_Month: 20, VCV_Daily_Week: 5}
    :return:
    '''

    # 获取日频率量价数据
    start_date = start_date.strftime('%Y%m%d')
    end_date = end_date.strftime('%Y%m%d')
    start_date_ago = utils.get_shifted_date(start_date, rolling_window, date_type='trading')
    query = (
        "select S_INFO_WINDCODE, TRADE_DT, S_DQ_AMOUNT from ASHAREEODPRICES "
        "where TRADE_DT between %s and %s and S_DQ_AMOUNT is not null "
    )
    data = pd.read_sql_query(query, STOCK_DB_WIND, params=(start_date_ago, end_date))
    data['TRADE_DT'] = pd.to_datetime(data["TRADE_DT"])
    data = data.pivot(index="TRADE_DT", columns="S_INFO_WINDCODE", values="S_DQ_AMOUNT")

    res = data.rolling(rolling_window).std() / data.rolling(rolling_window).mean()
    res *= -1
    res = res.loc[start_date: end_date, :]
    return res.replace([np.inf, -np.inf], np.nan)


def Panic_Small_Order_Pct_1min(start_date, end_date, window=20, decay_days=2):
    '''
    方正证券 - 显著效应、极端收益扭曲决策权重和“草木皆兵”因子——多因子选股系列研究之八
    Panic_Small_Order_Pct_1min: (“惊恐度”x收益率x个人投资者交易占比)的均值+标准差 [*反向]

    Parameters
    ----------
    start_date: 开始时间
    end_date: 结束时间
    window: 滚动窗口
    decay_days: 衰减天数

    Returns
    -------
    '''

    # 获取日频率量价数据
    start_date = start_date.strftime('%Y%m%d')
    end_date = end_date.strftime('%Y%m%d')
    start_date_ago = utils.get_shifted_date(start_date, window+decay_days, date_type='trading')
    ## 市场收益率
    query = (
        "select S_INFO_WINDCODE, TRADE_DT, (S_DQ_CLOSE / S_DQ_PRECLOSE - 1) AS RET from AINDEXEODPRICES "
        "where S_INFO_WINDCODE = %s and TRADE_DT between %s and %s "
    )
    mrk_ret = pd.read_sql_query(query, STOCK_DB_WIND, params=('000985.SH', start_date_ago, end_date))
    mrk_ret['TRADE_DT'] = pd.to_datetime(mrk_ret["TRADE_DT"])
    mrk_ret = mrk_ret.pivot(index='TRADE_DT', columns='S_INFO_WINDCODE', values='RET')
    ## 个股收益率
    query = (
        "select S_INFO_WINDCODE, TRADE_DT, (S_DQ_CLOSE / S_DQ_PRECLOSE - 1) AS RET from ASHAREEODPRICES "
        "where TRADE_DT between %s and %s "
    )
    stk_ret = pd.read_sql_query(query, STOCK_DB_WIND, params=(start_date_ago, end_date))
    stk_ret['TRADE_DT'] = pd.to_datetime(stk_ret["TRADE_DT"])
    stk_ret = stk_ret.pivot(index='TRADE_DT', columns='S_INFO_WINDCODE', values='RET')
    ## 个人投资者金额
    query = (
        "select S_INFO_WINDCODE, TRADE_DT, "
        "(BUY_VALUE_SMALL_ORDER + SELL_VALUE_SMALL_ORDER) / 2 AS SMALL_ORDER "
        "from ASHAREMONEYFLOW where TRADE_DT between %s and %s "
    )
    small_order = pd.read_sql_query(query, STOCK_DB_WIND, params=(start_date_ago, end_date))
    small_order['TRADE_DT'] = pd.to_datetime(small_order["TRADE_DT"])
    small_order = small_order.pivot(index='TRADE_DT', columns='S_INFO_WINDCODE', values='SMALL_ORDER')
    ## 成交金额
    query = (
        "select S_INFO_WINDCODE, TRADE_DT, S_DQ_AMOUNT from ASHAREEODPRICES "
        "where TRADE_DT between %s and %s and S_DQ_AMOUNT is not null"
    )
    amount = pd.read_sql_query(query, STOCK_DB_WIND, params=(start_date_ago, end_date))
    amount['TRADE_DT'] = pd.to_datetime(amount["TRADE_DT"])
    amount = amount.pivot(index='TRADE_DT', columns='S_INFO_WINDCODE', values='S_DQ_AMOUNT')

    # 实现因子逻辑
    ## 计算偏离项
    deviation = stk_ret.sub(mrk_ret.iloc[:, 0], axis=0).abs()
    ## 计算基准项
    base = stk_ret.abs().add(mrk_ret.abs().iloc[:, 0], axis=0) + 0.1
    ## 计算惊恐度
    panic_level = deviation / base
    ## 计算个人投资者占比
    small_order_pct = small_order / amount
    ## 计算决策分
    score = stk_ret * panic_level * small_order_pct

    res_mean = score.rolling(window).mean()
    res_std = score.rolling(window).std()
    res = res_mean + res_std
    res *= -1
    return res.loc[start_date: end_date, :]


def Market_Unique_1min(start_date, end_date, window=20, freq=1):
    '''
    方正证券 - 个股成交额的市场跟随性与“水中行舟” 因子——多因子选股系列研究之九
    Market_Unique_1min: 分钟成交额序列pearson相关系数绝对值的均值 [*反向]

    Parameters
    ----------
    start_date: 开始时间
    end_date: 结束时间
    window: 滚动窗口
    freq: 数据频率

    Returns
    -------
    '''

    # 获取 freq = 1 分钟频率量价数据
    start_date = start_date.strftime('%Y%m%d')
    end_date = end_date.strftime('%Y%m%d')
    start_date_ago = utils.get_shifted_date(start_date, window, date_type='trading')

    date_list = [date.strftime('%Y%m%d') for date in utils.get_exchange_trading_dates(start_date_ago, end_date)]
    df_unique = pd.DataFrame()
    for date in date_list:
        path = root_dir.format(str(freq), date, str(freq))
        if not os.path.exists(path):
            continue
        data = pd.read_csv(path)

        # 实现因子逻辑
        data['time'] = pd.to_datetime(data['tradingDay'].astype(str) + ' ' + data['tradingMinute'])
        df_close = data.pivot(index="time", columns="windCode", values="close")
        df_amount = data.pivot(index="time", columns="windCode", values="turnover")
        ## 计算分钟收益率
        df_pctchange = df_close.pct_change().iloc[1:]
        ## 计算分钟市场分化度
        df_pctchange_std = df_pctchange.std(axis=1)
        ## 计算不分化时刻
        flag = df_pctchange_std < df_pctchange_std.mean()
        ## 计算相关系数
        df = df_amount.iloc[1:][flag]
        corr = df.corr().abs().values
        np.fill_diagonal(corr, np.NaN)
        corr = pd.DataFrame(corr, columns=df.columns, index=df.columns).mean()
        corr = pd.DataFrame(corr, columns=[date])
        df_unique = pd.concat([df_unique, corr], axis=1)

    df_unique = df_unique.T
    df_unique.index = pd.to_datetime(df_unique.index)

    res_mean = df_unique.rolling(window).mean()
    res_std = df_unique.rolling(window).std()
    res = res_mean + res_std
    res *= -1
    return res.loc[start_date: end_date, :]


def Following_Coef_1min(start_date, end_date, window=20, freq=1, following_minute=5, moment_num=10, remove_minute=15):
    '''
    方正证券 - 大单成交后的跟随效应与“待著而救”因子——多因子选股系列研究之十一
    Following_Coef_1min: “日跟随系数”的均值+标准差

    Parameters
    ----------
    start_date: 开始时间
    end_date: 结束时间
    window: 滚动窗口
    freq: 数据频率
    following_minute: 跟随时间
    moment_num: “海量时刻”数
    remove_minute: 移除时间
    Returns
    -------
    '''

    # 获取 freq = 1 分钟频率量价数据
    start_date = start_date.strftime('%Y%m%d')
    end_date = end_date.strftime('%Y%m%d')
    start_date_ago = utils.get_shifted_date(start_date, window, date_type='trading')

    date_list = [date.strftime('%Y%m%d') for date in utils.get_exchange_trading_dates(start_date_ago, end_date)]
    following_coef = pd.DataFrame()
    for date in date_list:
        path = root_dir.format(str(freq), date, str(freq))
        if not os.path.exists(path):
            continue
        data = pd.read_csv(path)

        # 实现因子逻辑
        data['time'] = pd.to_datetime(data['tradingDay'].astype(str) + ' ' + data['tradingMinute'])
        pivot_volume = data.pivot(index="time", columns="windCode", values="volume")
        df_volume = pivot_volume.iloc[remove_minute:-following_minute]
        df_volume = df_volume.stack().reset_index()
        df_volume = df_volume.rename(columns={0: 'volume'})

        ## 计算海量时刻
        df_massive_moments = df_volume.groupby('windCode').apply(
            lambda group: group.nlargest(moment_num, 'volume')['time'].reset_index(drop=True)).T
        df_massive_moments = df_massive_moments.apply(lambda col: col.sort_values().reset_index(drop=True))

        ## 计算优势时刻
        def _func(col):
            start_minute = col[0]
            res_list = [start_minute]
            for x in col[1:]:
                if x - start_minute > pd.Timedelta(minutes=following_minute):
                    start_minute = x
                    res_list.append(start_minute)
                else:
                    res_list.append(np.NaN)
            return res_list

        df_advantageous_moment = df_massive_moments.apply(lambda col: _func(col))
        df_advantageous_moment_volume = df_advantageous_moment.apply(
            lambda col: col.map(lambda x: pivot_volume.loc[x, col.name] if not pd.isna(x) else np.NaN))
        ## 计算跟随时刻
        df_advantageous_moment_idx = df_advantageous_moment.apply(lambda col: pivot_volume.index.get_indexer_for(col))
        df_following_moment_volume = df_advantageous_moment_idx.apply(lambda col: col.map(
            lambda x: np.NaN if x == -1 else pivot_volume.loc[
                pivot_volume.index[[(x + i) for i in range(1, following_minute + 1)]], col.name].sum()))
        ## 计算跟随系数
        df_following_coef = df_advantageous_moment_volume / df_following_moment_volume
        df_following_coef_daily = df_following_coef.mean()
        df_following_coef_daily = pd.DataFrame(df_following_coef_daily, columns=[date])
        following_coef = pd.concat([following_coef, df_following_coef_daily], axis=1)

    following_coef = following_coef.T
    following_coef.index = pd.to_datetime(following_coef.index)
    following_coef = following_coef.replace([np.inf, -np.inf], np.nan)

    res_mean = following_coef.rolling(window).mean()
    res_std = following_coef.rolling(window).std()
    res = res_mean + res_std
    return res.loc[start_date: end_date, :]
