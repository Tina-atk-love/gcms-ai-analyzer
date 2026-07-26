#!/usr/bin/env python3
"""Nature Journal publication skills — standalone module."""
import numpy as np
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent / "output" / "agent_results"
NATURE_COLORS = {
    'categorical': ['#E64B35','#4DBBD5','#00A087','#3C5488','#F39B7F',
                    '#8491B4','#91D1C2','#DC0000','#7E6148','#B09C85'],
    'highlight': '#E64B35',
}
NATURE_SIZES = {'single':(3.5,2.6),'1.5col':(5.5,4.1),'double':(7.2,5.4)}

def _save_both(fig, base_path):
    """Save as both 600dpi TIFF and 150dpi PNG, return paths dict."""
    tiff_p = str(base_path) + '.tiff'
    png_p = str(base_path) + '.png'
    fig.savefig(tiff_p, dpi=600, format='tiff', pil_kwargs={'compression':'lzw'})
    fig.savefig(png_p, dpi=150, format='png')
    return {'tiff': tiff_p, 'png': png_p}

def generate_nature_figures(df, fig_type='all', size='single'):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler
    from scipy.stats import ttest_ind

    plt.rcParams.update({
        'font.family':'sans-serif','font.sans-serif':['Arial','Helvetica','Microsoft YaHei'],
        'font.size':7,'axes.labelsize':8,'axes.titlesize':9,'xtick.labelsize':7,'ytick.labelsize':7,
        'legend.fontsize':7,'figure.dpi':600,'savefig.dpi':600,'lines.linewidth':1.0,'lines.markersize':4,
        'axes.linewidth':0.5,'axes.spines.top':False,'axes.spines.right':False,'axes.grid':False,
        'figure.facecolor':'white','axes.facecolor':'white','axes.unicode_minus':False,
        'savefig.bbox':'tight','savefig.pad_inches':0.05,
    })

    fs = NATURE_SIZES.get(size, NATURE_SIZES['single'])
    plots_dir = OUTPUT_DIR / "plots" / "nature"
    plots_dir.mkdir(parents=True, exist_ok=True)
    colors = NATURE_COLORS['categorical']
    generated = []

    vc = 'area'
    if 'conc_g100g' in df.columns and df['conc_g100g'].notna().sum() > 5: vc = 'conc_g100g'
    elif 'amount' in df.columns and df['amount'].notna().sum() > 5: vc = 'amount'

    types = ['bar','pca','heatmap','volcano','boxplot'] if fig_type == 'all' else [fig_type]
    groups = sorted(df['group'].unique()) if 'group' in df.columns else ['All']

    for ft in types:
        try:
            base = plots_dir / f'Fig_{ft}_{size}'
            if ft == 'bar':
                top12 = df.groupby('compound')[vc].mean().nlargest(12).index
                fig, ax = plt.subplots(figsize=fs)
                ng = len(groups)
                for gi, grp in enumerate(groups):
                    m = df[(df['group']==grp)&(df['compound'].isin(top12))].groupby('compound')[vc].mean()
                    xp = np.arange(len(top12)) + gi*(0.8/ng)
                    ax.bar(xp, [m.get(c,0) for c in top12], 0.7/ng,
                           color=colors[gi%len(colors)], label=str(grp), edgecolor='white', lw=0.3)
                ax.set_xticks(np.arange(len(top12))+0.35)
                ax.set_xticklabels([str(c)[:12] for c in top12], rotation=45, ha='right', fontsize=6)
                ax.set_ylabel(vc)
                if ng > 1: ax.legend(frameon=False, fontsize=6)
                fig.tight_layout()
                generated.append({**_save_both(fig, base), 'type': ft})
                plt.close(fig)

            elif ft == 'pca':
                pv = df.pivot_table(values=vc, index='sample', columns='compound', aggfunc='mean').fillna(0)
                if pv.shape[0] < 3: continue
                X_s = StandardScaler().fit_transform(pv.values)
                pc = PCA(n_components=min(2, X_s.shape[0], X_s.shape[1]))
                X_p = pc.fit_transform(X_s)
                ev = pc.explained_variance_ratio_
                fig, ax = plt.subplots(figsize=fs)
                for gi, grp in enumerate(groups):
                    idxs = [i for i,s in enumerate(pv.index) if df[df['sample']==s]['group'].iloc[0]==grp]
                    if not idxs: continue
                    ax.scatter(X_p[idxs,0], X_p[idxs,1] if X_p.shape[1]>=2 else [0]*len(idxs),
                              c=[colors[gi%len(colors)]], s=25, label=str(grp), ec='white', lw=0.5)
                    for j in idxs:
                        ax.annotate(str(pv.index[j]).replace('.D',''), (X_p[j,0], X_p[j,1]), fontsize=5, alpha=0.7)
                ax.set_xlabel(f'PC1 ({ev[0]*100:.0f}%)')
                if X_p.shape[1]>=2: ax.set_ylabel(f'PC2 ({ev[1]*100:.0f}%)')
                if len(groups)>1: ax.legend(frameon=False, fontsize=6)
                fig.tight_layout()
                generated.append({**_save_both(fig, base), 'type': ft})
                plt.close(fig)

            elif ft == 'heatmap':
                pv = df.pivot_table(values=vc, index='sample', columns='compound', aggfunc='mean').fillna(0)
                dz = ((pv-pv.mean())/pv.std()).fillna(0)
                fig, ax = plt.subplots(figsize=(fs[0]*1.3, fs[1]))
                im = ax.imshow(dz.values, aspect='auto', cmap='RdBu_r', vmin=-2, vmax=2)
                ax.set_xticks(range(len(dz.columns)))
                ax.set_xticklabels([str(c)[:10] for c in dz.columns], rotation=90, fontsize=5)
                ax.set_yticks(range(len(dz.index)))
                ax.set_yticklabels([str(i).replace('.D','') for i in dz.index], fontsize=6)
                cb = fig.colorbar(im, ax=ax, shrink=0.6); cb.set_label('Z-score', fontsize=6)
                fig.tight_layout()
                generated.append({**_save_both(fig, base), 'type': ft})
                plt.close(fig)

            elif ft == 'volcano':
                if len(groups) >= 2:
                    g1,g2 = str(groups[0]), str(groups[1])
                    m1=df[df['group']==g1].groupby('compound')[vc].mean()
                    m2=df[df['group']==g2].groupby('compound')[vc].mean()
                    cm=list(m1.index.intersection(m2.index))
                    if len(cm)<3: continue
                    fc=np.log2((m2[cm].values+1e-6)/(m1[cm].values+1e-6))
                    pvs=[]
                    for c in cm:
                        v1=df[(df['group']==g1)&(df['compound']==c)][vc]
                        v2=df[(df['group']==g2)&(df['compound']==c)][vc]
                        try: _,pv=ttest_ind(v1,v2); pvs.append(max(pv,1e-300))
                        except: pvs.append(1.0)
                    nlp=-np.log10(pvs)
                    fig,ax=plt.subplots(figsize=fs)
                    sig=(np.abs(fc)>1)&(nlp>1.3)
                    ax.scatter(fc[~sig],nlp[~sig],s=8,c='#999',alpha=0.5,ec='none')
                    ax.scatter(fc[sig],nlp[sig],s=14,c=NATURE_COLORS['highlight'],alpha=0.8,ec='none')
                    for i in np.argsort(nlp)[-5:]:
                        if nlp[i]>1.3: ax.annotate(str(cm[i])[:15],(fc[i],nlp[i]),fontsize=5)
                    ax.axhline(1.3,ls='--',lw=0.5,c='grey',alpha=0.5)
                    ax.set_xlabel(f'log2({g2}/{g1})'); ax.set_ylabel('-log10(p)')
                    fig.tight_layout()
                    generated.append({**_save_both(fig, base), 'type': ft})
                    plt.close(fig)

            elif ft == 'boxplot':
                top8=df.groupby('compound')[vc].mean().nlargest(8).index
                sub=df[df['compound'].isin(top8)]
                fig,ax=plt.subplots(figsize=(fs[0],fs[1]*1.2))
                ng=len(groups)
                for ci,comp in enumerate(top8):
                    for gi,grp in enumerate(groups):
                        v=sub[(sub['compound']==comp)&(sub['group']==grp)][vc]
                        if len(v)==0: continue
                        pos=ci*(ng+1)+gi
                        ax.boxplot(v,positions=[pos],widths=0.6,patch_artist=True,showfliers=False,
                                   manage_ticks=False,
                                   boxprops=dict(facecolor=colors[gi%len(colors)],alpha=0.7,lw=0.5),
                                   whiskerprops=dict(lw=0.5),capprops=dict(lw=0.5),
                                   medianprops=dict(lw=0.8,color='black'))
                ax.set_xticks([ci*(ng+1)+ng/2-0.5 for ci in range(len(top8))])
                ax.set_xticklabels([str(c)[:10] for c in top8],rotation=45,ha='right',fontsize=6)
                ax.set_ylabel(vc)
                if ng>1:
                    from matplotlib.patches import Patch
                    ax.legend([Patch(facecolor=colors[i]) for i in range(ng)],
                             [str(g) for g in groups],frameon=False,fontsize=6)
                fig.tight_layout()
                generated.append({**_save_both(fig, base), 'type': ft})
                plt.close(fig)

        except Exception as e:
            generated.append({'error': str(e), 'type': ft})

    ok = [g for g in generated if 'tiff' in g]
    return {"status":"done","files":generated,"count":len(ok),"size":size,"format":"TIFF 600dpi"}
