import React, { useState, useCallback, useEffect } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Loader2, CheckCircle2, AlertCircle, ExternalLink, Trash2 } from 'lucide-react';
import { useApi } from '@/hooks/use-api';
import { useToast } from '@/hooks/use-toast';

interface OutputPortInfo {
  name: string;
  assetType?: string;
  assetIdentifier?: string;
}

interface ProductInfo {
  id: string;
  name: string;
  outputPorts: OutputPortInfo[];
}

interface ExistingSpace {
  id: string;
  space_id: string;
  space_name: string;
  space_url?: string;
  status: string;
  created_at: string;
}

interface GenieSpaceDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  products: ProductInfo[];
  onSuccess?: () => void;
}

type DialogState = 'idle' | 'creating' | 'success' | 'error';

export default function GenieSpaceDialog({ open, onOpenChange, products, onSuccess }: GenieSpaceDialogProps) {
  const { post, get, del } = useApi();
  const { toast } = useToast();

  const [state, setState] = useState<DialogState>('idle');
  const [errorMessage, setErrorMessage] = useState('');
  const [spaceUrl, setSpaceUrl] = useState<string | null>(null);
  const [spaceName, setSpaceName] = useState('');
  const [existingSpaces, setExistingSpaces] = useState<ExistingSpace[]>([]);
  const [deletingSpaceId, setDeletingSpaceId] = useState<string | null>(null);

  // Track which tables are selected (all selected by default)
  const allTables = products.flatMap(p =>
    (p.outputPorts || [])
      .filter(port => port.assetIdentifier)
      .map(port => `${p.id}::${port.assetIdentifier}`)
  );
  const [selectedTables, setSelectedTables] = useState<Set<string>>(new Set(allTables));

  // Fetch existing Genie Spaces when dialog opens
  const fetchExistingSpaces = useCallback(async () => {
    try {
      const resp = await get<ExistingSpace[]>('/api/genie-spaces/my');
      if (resp.data && Array.isArray(resp.data)) {
        setExistingSpaces(resp.data);
      }
    } catch {
      // Not critical
    }
  }, [get]);

  // Reset state when dialog opens
  const handleOpenChange = useCallback((isOpen: boolean) => {
    if (isOpen) {
      setState('idle');
      setErrorMessage('');
      setSpaceUrl(null);
      setSpaceName('');
      const tables = products.flatMap(p =>
        (p.outputPorts || [])
          .filter(port => port.assetIdentifier)
          .map(port => `${p.id}::${port.assetIdentifier}`)
      );
      setSelectedTables(new Set(tables));
      fetchExistingSpaces();
    }
    onOpenChange(isOpen);
  }, [onOpenChange, products, fetchExistingSpaces]);

  const toggleTable = (key: string) => {
    setSelectedTables(prev => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const toggleAllForProduct = (product: ProductInfo) => {
    const productKeys = (product.outputPorts || [])
      .filter(port => port.assetIdentifier)
      .map(port => `${product.id}::${port.assetIdentifier}`);
    const allSelected = productKeys.every(k => selectedTables.has(k));

    setSelectedTables(prev => {
      const next = new Set(prev);
      productKeys.forEach(k => {
        if (allSelected) {
          next.delete(k);
        } else {
          next.add(k);
        }
      });
      return next;
    });
  };

  const selectedCount = selectedTables.size;

  const handleDelete = async (spaceId: string) => {
    setDeletingSpaceId(spaceId);
    try {
      await del(`/api/genie-spaces/${spaceId}`);
      setExistingSpaces(prev => prev.filter(s => s.space_id !== spaceId));
      toast({ title: 'Genie Space Deleted', description: 'The Genie Space has been deleted.' });
    } catch (err: any) {
      toast({ title: 'Error', description: err.message || 'Failed to delete Genie Space.', variant: 'destructive' });
    } finally {
      setDeletingSpaceId(null);
    }
  };

  const handleCreate = async () => {
    if (selectedCount === 0) return;

    setState('creating');
    setErrorMessage('');

    try {
      const productIds = products.map(p => p.id);
      const response = await post('/api/data-products/genie-space', { product_ids: productIds });

      if (response.error) {
        throw new Error(response.error);
      }

      // Build a display name from the first product
      const displayName = products.length === 1
        ? `${products[0].name} - Genie Space`
        : `Genie Space (${products.length} products)`;
      setSpaceName(displayName);

      // Wait for the backend to create the space asynchronously, then poll
      setTimeout(async () => {
        try {
          const spacesResp = await get<any[]>('/api/genie-spaces/my');
          if (spacesResp.data && Array.isArray(spacesResp.data) && spacesResp.data.length > 0) {
            // Find the most recently created space (usually first in the list)
            const latestSpace = spacesResp.data[0];
            setSpaceUrl(latestSpace.space_url || latestSpace.url || null);
          }
        } catch {
          // Not critical - URL is a convenience, creation still succeeded
        }
      }, 5000);

      setState('success');
      toast({ title: 'Genie Space Created', description: `${displayName} is being set up.` });
      onSuccess?.();
    } catch (err: any) {
      setState('error');
      setErrorMessage(err.message || 'Failed to create Genie Space. Please try again.');
      toast({ title: 'Error', description: err.message || 'Failed to create Genie Space.', variant: 'destructive' });
    }
  };

  // Extract the short table name from a fully qualified identifier
  const shortName = (identifier: string) => {
    const parts = identifier.split('.');
    return parts[parts.length - 1];
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[520px]">
        {state === 'success' ? (
          // --- Success state ---
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5 text-green-600" />
                Genie Space Created!
              </DialogTitle>
            </DialogHeader>
            <div className="py-4 space-y-3">
              <p className="text-sm text-muted-foreground">
                Your Genie Space is ready with {selectedCount} table{selectedCount !== 1 ? 's' : ''}.
              </p>
              {spaceName && (
                <p className="text-sm font-medium">{spaceName}</p>
              )}
            </div>
            <DialogFooter>
              {spaceUrl && (
                <Button variant="default" asChild>
                  <a href={spaceUrl} target="_blank" rel="noopener noreferrer">
                    <ExternalLink className="mr-2 h-4 w-4" />
                    Open Genie Space
                  </a>
                </Button>
              )}
              <Button variant="outline" onClick={() => handleOpenChange(false)}>
                Close
              </Button>
            </DialogFooter>
          </>
        ) : (
          // --- Idle / Creating / Error state ---
          <>
            <DialogHeader>
              <DialogTitle>Create Genie Space</DialogTitle>
              <DialogDescription>
                Create a Genie Space from this data product. The space will include
                all tables from the product's output ports.
              </DialogDescription>
            </DialogHeader>

            {/* Existing Genie Spaces */}
            {existingSpaces.length > 0 && (
              <>
                <div className="space-y-2">
                  <h4 className="text-sm font-medium text-muted-foreground">Existing Genie Spaces</h4>
                  {existingSpaces.map(space => (
                    <div key={space.space_id} className="flex items-center justify-between border rounded-md p-2">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">{space.space_name}</p>
                        <p className="text-xs text-muted-foreground">
                          {new Date(space.created_at).toLocaleDateString()}
                          {space.status !== 'active' && (
                            <Badge variant="secondary" className="ml-2 text-xs">{space.status}</Badge>
                          )}
                        </p>
                      </div>
                      <div className="flex items-center gap-1 ml-2">
                        {space.space_url && (
                          <Button variant="ghost" size="sm" asChild>
                            <a href={space.space_url} target="_blank" rel="noopener noreferrer">
                              <ExternalLink className="h-3.5 w-3.5" />
                            </a>
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDelete(space.space_id)}
                          disabled={deletingSpaceId === space.space_id}
                        >
                          {deletingSpaceId === space.space_id ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Trash2 className="h-3.5 w-3.5 text-destructive" />
                          )}
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
                <Separator />
              </>
            )}

            <ScrollArea className="max-h-[340px]">
              <div className="space-y-4 pr-2">
                {products.map(product => {
                  const ports = (product.outputPorts || []).filter(port => port.assetIdentifier);
                  const productKeys = ports.map(port => `${product.id}::${port.assetIdentifier}`);
                  const allSelected = productKeys.length > 0 && productKeys.every(k => selectedTables.has(k));
                  const someSelected = productKeys.some(k => selectedTables.has(k));

                  return (
                    <div key={product.id} className="border rounded-lg p-3">
                      <div className="flex items-center gap-2 mb-2">
                        <Checkbox
                          checked={allSelected ? true : someSelected ? 'indeterminate' : false}
                          onCheckedChange={() => toggleAllForProduct(product)}
                          disabled={state === 'creating'}
                        />
                        <span className="font-medium text-sm">{product.name}</span>
                      </div>
                      {ports.length > 0 ? (
                        <div className="ml-6 space-y-1.5">
                          {ports.map(port => {
                            const key = `${product.id}::${port.assetIdentifier}`;
                            return (
                              <div key={key} className="flex items-center gap-2">
                                <Checkbox
                                  checked={selectedTables.has(key)}
                                  onCheckedChange={() => toggleTable(key)}
                                  disabled={state === 'creating'}
                                />
                                <span className="text-sm text-muted-foreground font-mono">
                                  {shortName(port.assetIdentifier!)}
                                </span>
                                {port.assetType && (
                                  <Badge variant="secondary" className="text-xs">
                                    {port.assetType}
                                  </Badge>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      ) : (
                        <p className="ml-6 text-xs text-muted-foreground italic">
                          No tables found in output ports
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            </ScrollArea>

            <Separator />

            <div className="flex items-center justify-between text-sm text-muted-foreground">
              <span>
                {selectedCount} table{selectedCount !== 1 ? 's' : ''} will be included
              </span>
            </div>

            {state === 'error' && errorMessage && (
              <div className="flex items-start gap-2 p-3 rounded-md bg-destructive/10 text-destructive text-sm">
                <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                <span>{errorMessage}</span>
              </div>
            )}

            <DialogFooter>
              <Button variant="outline" onClick={() => handleOpenChange(false)} disabled={state === 'creating'}>
                Cancel
              </Button>
              <Button onClick={handleCreate} disabled={state === 'creating' || selectedCount === 0}>
                {state === 'creating' ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Creating...
                  </>
                ) : (
                  'Create Genie Space'
                )}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
