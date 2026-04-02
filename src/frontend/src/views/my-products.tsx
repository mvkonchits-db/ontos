import { useState, useEffect, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useLocation } from 'react-router-dom';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card';
import { Package, ExternalLink, ShoppingBag, Search, X, LayoutList, Network, Database, Table2, Grid2X2, Loader2 } from 'lucide-react';
import { CardSkeleton } from '@/components/common/list-view-skeleton';
import { DataDomainMiniGraph } from '@/components/data-domains/data-domain-mini-graph';
import { useDomains } from '@/hooks/use-domains';
import { useViewModeStore } from '@/stores/view-mode-store';
import { type DataProduct } from '@/types/data-product';
import { type DataDomain } from '@/types/data-domain';
import { type DatasetListItem, DATASET_STATUS_LABELS, DATASET_STATUS_COLORS } from '@/types/dataset';
import { useApi } from '@/hooks/use-api';
import { cn } from '@/lib/utils';
import useBreadcrumbStore from '@/stores/breadcrumb-store';

type AssetType = 'products' | 'datasets';

export default function MyProducts() {
  const { t } = useTranslation('home');
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { domains, loading: domainsLoading, getDomainName } = useDomains();
  const { domainBrowserStyle, setDomainBrowserStyle, tilesPerRow, setTilesPerRow } = useViewModeStore();
  const api = useApi();
  const setStaticSegments = useBreadcrumbStore((state) => state.setStaticSegments);

  const [products, setProducts] = useState<DataProduct[]>([]);
  const [datasets, setDatasets] = useState<DatasetListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [datasetsLoading, setDatasetsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState('');
  const [selectedDomainId, setSelectedDomainId] = useState<string | null>(null);
  const [assetType, setAssetType] = useState<AssetType>('products');
  const [exactMatchesOnly, setExactMatchesOnly] = useState(false);
  const [matchSets, setMatchSets] = useState<{ ids: Set<string>; namesLower: Set<string> } | null>(null);
  const [selectedDomainDetails, setSelectedDomainDetails] = useState<DataDomain | null>(null);
  const [domainDetailsLoading, setDomainDetailsLoading] = useState(false);
  const [graphFadeIn, setGraphFadeIn] = useState(false);

  const gridClass = useMemo(() => {
    switch (tilesPerRow) {
      case 1: return 'grid grid-cols-1 gap-4';
      case 2: return 'grid grid-cols-1 sm:grid-cols-2 gap-4';
      case 3: return 'grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4';
      default: return 'grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4';
    }
  }, [tilesPerRow]);

  const loadSubscriptions = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const resp = await api.get<DataProduct[]>('/api/data-products/my-subscriptions');
      const data = resp.data;
      setProducts(Array.isArray(data) ? data : []);
    } catch (e) {
      console.warn('Failed to fetch my subscriptions:', e);
      setError(e instanceof Error ? e.message : 'Failed to load');
      setProducts([]);
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadSubscribedDatasets = useCallback(async () => {
    try {
      setDatasetsLoading(true);
      const resp = await fetch('/api/datasets/my-subscriptions');
      if (!resp.ok) {
        if (resp.status === 401) {
          setDatasets([]);
          return;
        }
        throw new Error(`HTTP ${resp.status}`);
      }
      const data = await resp.json();
      setDatasets(Array.isArray(data) ? data : []);
    } catch (e) {
      console.warn('Failed to fetch subscribed datasets:', e);
      setDatasets([]);
    } finally {
      setDatasetsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSubscriptions();
  }, [loadSubscriptions]);

  useEffect(() => {
    if (assetType === 'datasets') {
      loadSubscribedDatasets();
    }
  }, [assetType, loadSubscribedDatasets]);

  useEffect(() => {
    setStaticSegments([{ label: t('myProducts.title'), path: '/my-products' }]);
    return () => setStaticSegments([]);
  }, [setStaticSegments, t]);

  const loadDomainDetails = useCallback(async (domainId: string) => {
    try {
      setDomainDetailsLoading(true);
      const resp = await fetch(`/api/data-domains/${domainId}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data: DataDomain = await resp.json();
      setSelectedDomainDetails(data);
    } catch (e) {
      setSelectedDomainDetails(null);
    } finally {
      setDomainDetailsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (domainBrowserStyle === 'graph' && selectedDomainId) {
      loadDomainDetails(selectedDomainId);
    } else if (domainBrowserStyle === 'graph' && !selectedDomainId && domains.length > 0) {
      const rootDomain = domains.find(d => !d.parent_id) || domains[0];
      if (rootDomain) setSelectedDomainId(rootDomain.id);
    }
  }, [domainBrowserStyle, selectedDomainId, domains, loadDomainDetails]);

  useEffect(() => {
    setGraphFadeIn(false);
    const raf = requestAnimationFrame(() => setGraphFadeIn(true));
    return () => cancelAnimationFrame(raf);
  }, [selectedDomainDetails?.id]);

  const sortedDomains = useMemo(() => {
    if (!domains?.length) return [];
    const childrenMap = new Map<string | null, DataDomain[]>();
    domains.forEach(d => {
      const parentId = d.parent_id || null;
      if (!childrenMap.has(parentId)) childrenMap.set(parentId, []);
      childrenMap.get(parentId)!.push(d);
    });
    childrenMap.forEach(children => children.sort((a, b) => a.name.localeCompare(b.name)));
    const result: DataDomain[] = [];
    const add = (domain: DataDomain, depth = 0) => {
      result.push({ ...domain, _depth: depth } as DataDomain & { _depth: number });
      (childrenMap.get(domain.id) || []).forEach(c => add(c, depth + 1));
    };
    (childrenMap.get(null) || []).forEach(root => add(root));
    return result;
  }, [domains]);

  useEffect(() => {
    if (!selectedDomainId) {
      setMatchSets(null);
      return;
    }
    const selected = domains.find(d => d.id === selectedDomainId);
    if (!selected) {
      const byName = domains.find(d => d.name.toLowerCase() === selectedDomainId.toLowerCase());
      if (byName) {
        setMatchSets({ ids: new Set([byName.id]), namesLower: new Set([byName.name.toLowerCase()]) });
      } else {
        setMatchSets({ ids: new Set([selectedDomainId]), namesLower: new Set([selectedDomainId.toLowerCase()]) });
      }
      return;
    }
    if (exactMatchesOnly) {
      setMatchSets({ ids: new Set([selectedDomainId]), namesLower: new Set([selected.name.toLowerCase()]) });
      return;
    }
    const ids = new Set<string>();
    const namesLower = new Set<string>();
    const childrenByParent = new Map<string, DataDomain[]>();
    domains.forEach(d => {
      if (d.parent_id) {
        if (!childrenByParent.has(d.parent_id)) childrenByParent.set(d.parent_id, []);
        childrenByParent.get(d.parent_id)!.push(d);
      }
    });
    const queue: DataDomain[] = [selected];
    while (queue.length > 0) {
      const d = queue.shift()!;
      ids.add(d.id);
      namesLower.add(d.name.toLowerCase());
      (childrenByParent.get(d.id) || []).forEach(c => queue.push(c));
    }
    setMatchSets({ ids, namesLower });
  }, [selectedDomainId, exactMatchesOnly, domains]);

  const filteredProducts = useMemo(() => {
    let list = products;
    if (selectedDomainId && matchSets) {
      list = list.filter(p => {
        const raw = p?.domain != null ? String(p.domain) : '';
        const lower = raw.toLowerCase();
        return raw && (matchSets.ids.has(raw) || matchSets.namesLower.has(lower));
      });
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter(p =>
        p.name?.toLowerCase().includes(q) ||
        p.description?.purpose?.toLowerCase().includes(q) ||
        p.description?.usage?.toLowerCase().includes(q)
      );
    }
    return list;
  }, [products, selectedDomainId, matchSets, searchQuery]);

  const filteredDatasets = useMemo(() => {
    if (!searchQuery.trim()) return datasets;
    const q = searchQuery.toLowerCase();
    return datasets.filter(d =>
      d.name?.toLowerCase().includes(q) ||
      d.full_path?.toLowerCase().includes(q) ||
      d.contract_name?.toLowerCase().includes(q)
    );
  }, [datasets, searchQuery]);

  const hasProducts = products.length > 0;
  const hasDatasets = datasets.length > 0;
  const showAssetToggle = hasProducts || hasDatasets;

  const handleOpenProduct = (e: React.MouseEvent, productId: string) => {
    e.stopPropagation();
    navigate(`${pathname}/${productId}`);
  };

  const handleOpenDataset = (e: React.MouseEvent, datasetId: string) => {
    e.stopPropagation();
    navigate(`/datasets/${datasetId}`);
  };

  const handleBrowseMarketplace = () => navigate('/');

  if (loading && assetType === 'products') {
    return (
      <div className="flex flex-col gap-4 p-4">
        <div>
          <div className="h-8 w-48 rounded-md bg-muted animate-pulse mb-2" />
          <div className="h-4 w-96 rounded-md bg-muted animate-pulse" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {[...Array(8)].map((_, i) => (
            <CardSkeleton key={i} titleWidth="w-36" descriptionWidth="w-48" contentRows={2} />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col gap-4 p-4">
        <p className="text-destructive">{error}</p>
        <Button variant="outline" onClick={loadSubscriptions}>Retry</Button>
      </div>
    );
  }

  const showEmpty = (assetType === 'products' && filteredProducts.length === 0) || (assetType === 'datasets' && (datasetsLoading ? false : filteredDatasets.length === 0));
  const emptyNoSubscriptions = assetType === 'products' ? !hasProducts : !hasDatasets;

  return (
    <div className="flex flex-col gap-4 p-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{t('myProducts.title')}</h1>
        <p className="text-muted-foreground mt-1">{t('myProducts.description')}</p>
      </div>

      {/* Search Bar */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          type="search"
          placeholder={assetType === 'products' ? t('marketplace.searchPlaceholder') : t('marketplace.searchDatasetsPlaceholder')}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="pl-10 h-12 text-base"
        />
        {searchQuery && (
          <Button variant="ghost" size="sm" className="absolute right-2 top-1/2 -translate-y-1/2 h-7 w-7 p-0" onClick={() => setSearchQuery('')}>
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>

      {/* Browse Data Domains - only for products */}
      {assetType === 'products' && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm font-medium">{t('marketplace.browseDataDomains')}</div>
            <div className="flex items-center gap-4">
              {selectedDomainId && (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">{t('marketplace.exactMatchOnly')}</span>
                  <Switch checked={exactMatchesOnly} onCheckedChange={(v) => setExactMatchesOnly(!!v)} />
                </div>
              )}
              <div className="inline-flex items-center gap-1 p-0.5 bg-muted rounded-md">
                <Button variant={domainBrowserStyle === 'pills' ? 'default' : 'ghost'} size="sm" onClick={() => setDomainBrowserStyle('pills')} className="h-7 px-2 gap-1" title={t('marketplace.domainView.pills')}>
                  <LayoutList className="h-3.5 w-3.5" />
                  <span className="sr-only sm:not-sr-only sm:inline text-xs">{t('marketplace.domainView.pills')}</span>
                </Button>
                <Button variant={domainBrowserStyle === 'graph' ? 'default' : 'ghost'} size="sm" onClick={() => setDomainBrowserStyle('graph')} className="h-7 px-2 gap-1" title={t('marketplace.domainView.graph')}>
                  <Network className="h-3.5 w-3.5" />
                  <span className="sr-only sm:not-sr-only sm:inline text-xs">{t('marketplace.domainView.graph')}</span>
                </Button>
              </div>
            </div>
          </div>
          {domainsLoading || domainDetailsLoading ? (
            <div className="flex items-center gap-2 text-muted-foreground h-[220px] justify-center border rounded-lg bg-muted/20">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span className="text-sm">{t('marketplace.loadingDomains')}</span>
            </div>
          ) : domainBrowserStyle === 'pills' ? (
            <div className="flex flex-wrap gap-2">
              <Button variant={selectedDomainId === null ? 'default' : 'outline'} size="sm" onClick={() => setSelectedDomainId(null)} className="rounded-full">
                {t('marketplace.allDomains')}
              </Button>
              {sortedDomains.map(domain => {
                const parentDomain = domain.parent_id ? domains.find(d => d.id === domain.parent_id) : null;
                return (
                  <HoverCard key={domain.id} openDelay={300} closeDelay={100}>
                    <HoverCardTrigger asChild>
                      <Button variant={selectedDomainId === domain.id ? 'default' : 'outline'} size="sm" onClick={() => setSelectedDomainId(domain.id)} className="rounded-full">
                        {domain.name}
                      </Button>
                    </HoverCardTrigger>
                    <HoverCardContent side="bottom" align="start" className="w-72">
                      <div className="space-y-2">
                        <div className="flex items-start gap-2">
                          <Database className="h-4 w-4 mt-0.5 text-primary flex-shrink-0" />
                          <div>
                            <h4 className="text-sm font-semibold">{domain.name}</h4>
                            {parentDomain && <p className="text-xs text-muted-foreground">{t('marketplace.domainInfo.parentDomain')}: {parentDomain.name}</p>}
                          </div>
                        </div>
                        {domain.description && <p className="text-xs text-muted-foreground line-clamp-3">{domain.description}</p>}
                        {domain.children_count !== undefined && domain.children_count > 0 && (
                          <p className="text-xs text-muted-foreground">{t('marketplace.domainInfo.childDomains', { count: domain.children_count })}</p>
                        )}
                      </div>
                    </HoverCardContent>
                  </HoverCard>
                );
              })}
            </div>
          ) : selectedDomainDetails ? (
            <div className={cn('transition-opacity duration-300', graphFadeIn ? 'opacity-100' : 'opacity-0')}>
              <DataDomainMiniGraph currentDomain={selectedDomainDetails} onNodeClick={(id) => setSelectedDomainId(id)} />
            </div>
          ) : (
            <div className="h-[220px] border rounded-lg overflow-hidden bg-muted/20 w-full flex items-center justify-center text-muted-foreground">
              {t('marketplace.selectDomainForGraph')}
            </div>
          )}
        </div>
      )}

      {/* Browse: Data Products / Datasets & Tiles per row */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div />
        <div className="flex items-center gap-4 flex-wrap">
          {showAssetToggle && (
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">{t('marketplace.browseAssetType')}</span>
              <div className="inline-flex items-center gap-1 p-0.5 bg-muted rounded-md">
                <Button variant={assetType === 'products' ? 'default' : 'ghost'} size="sm" onClick={() => setAssetType('products')} className="h-7 px-3 gap-1.5">
                  <Package className="h-3.5 w-3.5" />
                  {t('marketplace.assetTypes.products')}
                </Button>
                <Button variant={assetType === 'datasets' ? 'default' : 'ghost'} size="sm" onClick={() => setAssetType('datasets')} className="h-7 px-3 gap-1.5">
                  <Table2 className="h-3.5 w-3.5" />
                  {t('marketplace.assetTypes.datasets')}
                </Button>
              </div>
            </div>
          )}
          <div className="flex items-center gap-2">
            <Grid2X2 className="h-4 w-4 text-muted-foreground" />
            <Select value={String(tilesPerRow)} onValueChange={(v) => setTilesPerRow(Number(v) as 1 | 2 | 3 | 4)}>
              <SelectTrigger className="w-[100px] h-7 text-xs">
                <SelectValue placeholder={t('marketplace.tilesPerRow.placeholder')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="1">{t('marketplace.tilesPerRow.one')}</SelectItem>
                <SelectItem value="2">{t('marketplace.tilesPerRow.two')}</SelectItem>
                <SelectItem value="3">{t('marketplace.tilesPerRow.three')}</SelectItem>
                <SelectItem value="4">{t('marketplace.tilesPerRow.four')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>

      {/* Empty state - no subscriptions at all */}
      {showEmpty && emptyNoSubscriptions && (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center py-12">
            <ShoppingBag className="h-12 w-12 text-muted-foreground mb-4" />
            <p className="text-muted-foreground text-center">{t('myProducts.empty')}</p>
            <Button className="mt-4" onClick={handleBrowseMarketplace}>{t('myProducts.browseMarketplace')}</Button>
          </CardContent>
        </Card>
      )}

      {/* Empty state - filters returned no results */}
      {showEmpty && !emptyNoSubscriptions && (
        <div className="text-center py-12 text-muted-foreground">
          {assetType === 'products' ? (
            <>
              <Package className="h-12 w-12 mx-auto mb-4 opacity-30" />
              <p>{t('marketplace.products.noProducts')}</p>
              <p className="text-sm mt-1">{t('marketplace.products.adjustFilters')}</p>
            </>
          ) : (
            <>
              <Table2 className="h-12 w-12 mx-auto mb-4 opacity-30" />
              <p>{t('marketplace.datasets.noDatasets')}</p>
              <p className="text-sm mt-1">{t('marketplace.datasets.adjustFilters')}</p>
            </>
          )}
        </div>
      )}

      {/* Products list */}
      {assetType === 'products' && filteredProducts.length > 0 && (
        <>
          <div className="text-sm text-muted-foreground">
            {filteredProducts.length} {filteredProducts.length === 1 ? 'product' : 'products'} available
          </div>
          <div className={gridClass}>
            {filteredProducts.map((product) => {
              const domainStr = product?.domain != null ? String(product.domain) : '';
              const domainLabel = getDomainName(domainStr) || domainStr || t('marketplace.products.unknown');
              const description = product.description?.purpose || product.description?.usage || '';
              const owner = product.team?.members?.[0]?.username || product.team?.name || t('marketplace.products.unknown');
              return (
                <Card
                  key={product.id || product.name}
                  className={cn('cursor-pointer transition-all hover:shadow-md hover:border-primary/30 border-primary/20 bg-primary/5')}
                  onClick={() => product.id && navigate(`${pathname}/${product.id}`)}
                >
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <Package className="h-4 w-4 text-primary flex-shrink-0" />
                        <CardTitle className="text-base truncate">{product.name || 'Untitled'}</CardTitle>
                      </div>
                      {product.id && (
                        <Button variant="ghost" size="sm" className="h-6 w-6 p-0 hover:bg-primary/10" onClick={(e) => handleOpenProduct(e, product.id!)} title={t('marketplace.openInDetails')}>
                          <ExternalLink className="h-3.5 w-3.5 text-muted-foreground hover:text-primary" />
                        </Button>
                      )}
                    </div>
                    {description && <CardDescription className="line-clamp-2 text-sm">{description}</CardDescription>}
                  </CardHeader>
                  <CardContent className="pt-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Badge variant="secondary" className="text-xs">{domainLabel}</Badge>
                      {product.status && <Badge variant="outline" className="text-xs">{product.status}</Badge>}
                    </div>
                    <p className="text-xs text-muted-foreground mt-2 truncate">{t('marketplace.products.owner')}: {owner}</p>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </>
      )}

      {/* Datasets list */}
      {assetType === 'datasets' && (datasetsLoading ? (
        <div className="flex items-center justify-center h-48">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      ) : filteredDatasets.length > 0 && (
        <>
          <div className="text-sm text-muted-foreground">
            {filteredDatasets.length} {filteredDatasets.length === 1 ? 'dataset' : 'datasets'} available
          </div>
          <div className={gridClass}>
            {filteredDatasets.map((dataset) => {
              const statusLabel = DATASET_STATUS_LABELS[dataset.status] || dataset.status;
              const statusColorClass = DATASET_STATUS_COLORS[dataset.status] || '';
              return (
                <Card
                  key={dataset.id}
                  className={cn('cursor-pointer transition-all hover:shadow-md hover:border-primary/30 border-primary/20 bg-primary/5')}
                  onClick={() => dataset.id && navigate(`/datasets/${dataset.id}`)}
                >
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <Table2 className="h-4 w-4 text-primary flex-shrink-0" />
                        <CardTitle className="text-base truncate">{dataset.name || 'Untitled'}</CardTitle>
                      </div>
                      {dataset.id && (
                        <Button variant="ghost" size="sm" className="h-6 w-6 p-0 hover:bg-primary/10" onClick={(e) => handleOpenDataset(e, dataset.id!)} title={t('marketplace.openInDetails')}>
                          <ExternalLink className="h-3.5 w-3.5 text-muted-foreground hover:text-primary" />
                        </Button>
                      )}
                    </div>
                    {dataset.description && <CardDescription className="line-clamp-2 text-sm">{dataset.description}</CardDescription>}
                  </CardHeader>
                  <CardContent className="pt-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Badge className={cn('text-xs', statusColorClass)}>{statusLabel}</Badge>
                      {dataset.instance_count !== undefined && dataset.instance_count > 0 && (
                        <Badge variant="outline" className="text-xs">{dataset.instance_count} instance{dataset.instance_count !== 1 ? 's' : ''}</Badge>
                      )}
                      {dataset.contract_name && <Badge variant="secondary" className="text-xs">{dataset.contract_name}</Badge>}
                    </div>
                    {dataset.owner_team_name && (
                      <p className="text-xs text-muted-foreground mt-2 truncate">{t('marketplace.datasets.owner')}: {dataset.owner_team_name}</p>
                    )}
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </>
      ))}
    </div>
  );
}
