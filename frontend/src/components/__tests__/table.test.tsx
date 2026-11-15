import { renderToString } from 'react-dom/server';
import { describe, it, expect } from 'vitest';
import { FinancialTable, Column } from '../financial/FinancialTable';

interface TestItem {
  id: string;
  symbol: string;
  price: number;
}

describe('FinancialTable component', () => {
  const columns: Column<TestItem>[] = [
    { key: 'symbol', title: '代码', dataIndex: 'symbol', sortable: true },
    {
      key: 'price',
      title: '最新价',
      dataIndex: 'price',
      align: 'right',
      render: (val) => `$${val}`,
    },
  ];

  const testData: TestItem[] = [
    { id: '1', symbol: 'AAPL', price: 228.5 },
    { id: '2', symbol: 'NVDA', price: 145.8 },
  ];

  it('renders table headers and rows accurately', () => {
    const html = renderToString(
      <FinancialTable<TestItem>
        columns={columns}
        data={testData}
        rowKey={(r) => r.id}
      />
    );

    expect(html).toContain('代码');
    expect(html).toContain('最新价');
    expect(html).toContain('AAPL');
    expect(html).toContain('$228.5');
    expect(html).toContain('NVDA');
    expect(html).toContain('$145.8');
  });

  it('renders empty message when data is empty', () => {
    const html = renderToString(
      <FinancialTable<TestItem>
        columns={columns}
        data={[]}
        rowKey={(r) => r.id}
        emptyText="暂无匹配的投资标的"
      />
    );

    expect(html).toContain('暂无匹配的投资标的');
  });

  it('renders loading skeleton when isLoading is true', () => {
    const html = renderToString(
      <FinancialTable<TestItem>
        columns={columns}
        data={testData}
        rowKey={(r) => r.id}
        isLoading={true}
      />
    );

    expect(html).toContain('animate-pulse');
    expect(html).not.toContain('AAPL');
  });

  it('renders pagination details when pagination prop is passed', () => {
    const html = renderToString(
      <FinancialTable<TestItem>
        columns={columns}
        data={testData}
        rowKey={(r) => r.id}
        pagination={{
          currentPage: 1,
          pageSize: 2,
          total: 10,
          onPageChange: () => {},
        }}
      />
    );

    expect(html).toContain('共');
    expect(html).toContain('10');
    expect(html).toContain('条记录');
    expect(html).toContain('第');
    expect(html).toContain('上一页');
    expect(html).toContain('下一页');
  });
});
